from typing import Dict, Any, Optional, AsyncGenerator
import zmq
import zmq.asyncio
import asyncio
import logging
import json
import uuid
from contextlib import asynccontextmanager
from ..models import (
    RequestBlock, ReplyBlock, StreamingBlock, 
    EndBlock, ErrorBlock, RequestStep
)
from ..utils import serialize_message, deserialize_message

class ClientDealer:
    """客户端 DEALER 实现，按需连接"""
    def __init__(
        self,
        router_address: str,
        context: Optional[zmq.asyncio.Context] = None,
        hwm: int = 1000,
        timeout: Optional[float] = None,
        logger = None
    ):
        self._router_address = router_address
        self._hwm = hwm
        self._timeout = timeout
        self._logger = logger or logging.getLogger(__name__)
        
        self._context = context or zmq.asyncio.Context.instance()
        self._socket = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._client_id = str(uuid.uuid4().hex)
        self._available_methods = {}  # 缓存可用方法        

    async def connect(self):
        """连接到路由器"""
        self._logger.info(f"Connecting to router at {self._router_address}, {self._socket}")
        if not self._socket:
            self._socket = self._context.socket(zmq.DEALER)
            self._socket.identity = self._client_id.encode()
            self._socket.set_hwm(self._hwm)
            self._socket.connect(self._router_address)
            self._connected = True
            self._logger.info(f"Connected to router at {self._router_address}, {self._socket}")

            # 连接后立即更新可用方法
            await self.discover_services()

    async def close(self):
        """关闭连接"""
        self._available_methods = {}
        if self._socket:
            self._socket.close()
            self._socket = None
        self._connected = False

    async def __aenter__(self):
        """实现异步上下文管理器入口"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """实现异步上下文管理器出口"""
        await self.close()

    async def discover_services(self, timeout: Optional[float] = None) -> Dict[str, Dict]:
        """发现可用的服务方法"""
        return await self.invoke("methods", timeout=timeout)

    async def discover_clusters(self, timeout: Optional[float] = None) -> Dict[str, Dict]:
        """发现可用的服务节点"""
        return await self.invoke("clusters", timeout=timeout)

    async def invoke(self, method: str, *args, timeout: Optional[float] = None, **kwargs) -> Dict[str, Dict]:
        """直接返回结果的调用
        内部方法不会包含分组所需的间隔句点。
        """
        if "." in method:
            results = []
            async for chunk in self._service_stream(method, *args, timeout=timeout, **kwargs):
                results.append(chunk)
            return results
        else:
            self._logger.info(f"Invoke method: {method}")
            return await self._inner_invoke(method, timeout)
    
    async def stream(self, method: str, *args, timeout: Optional[float] = None, **kwargs) -> AsyncGenerator[Any, None]:
        """返回异步生成器"""
        if "." in method:
            async for chunk in self._service_stream(method, *args, timeout=timeout, **kwargs):
                yield chunk
        else:
            result = await self._inner_invoke(method, timeout)
            yield result

    async def _inner_invoke(self, method: str, timeout: Optional[float] = None) -> Dict[str, Dict]:
        """直接内部服务调用"""
        if timeout is None:
            timeout = self._timeout

        if not self._connected:
            await self.connect()
        
        try:
            await self._socket.send_multipart([
                method.encode(),
                b""
            ])

            multipart = await asyncio.wait_for(
                self._socket.recv_multipart(),
                timeout=timeout
            )

            response = deserialize_message(multipart[-1])
            self._logger.info(f"Received invoke method response: {response}")

            if isinstance(response, ReplyBlock):
                self._available_methods = response.result
                return self._available_methods
            elif isinstance(response, ErrorBlock):
                raise RuntimeError(response.error)
            else:
                raise ValueError(f"Unexpected response type: {type(response)}")

        except asyncio.TimeoutError:
            raise TimeoutError(f"[{self._router_address}] Invoke '{method}' timeout")
        except Exception as e:
            self._logger.error(f"[{self._router_address}] Invoke '{method}' error: {e}")
            raise

    async def _service_stream(
        self,
        method: str,
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        """调用 DEALER 服务，返回异步生成器"""
        if not self._connected:
            await self.connect()

        if method not in self._available_methods:
            # 如果方法不在缓存中，尝试更新一次
            await self.discover_services()
            if method not in self._available_methods:
                raise RuntimeError(
                    f"[{self._router_address}] Streaming method '{method}' not found. "
                    f"[{self._router_address}] Available methods: {list(self._available_methods.keys())}"
                )

        request_id = str(uuid.uuid4())
        request = RequestBlock(
            request_id=request_id,
            func_name=method,
            request_step=RequestStep.READY,
            args=args,
            kwargs=kwargs
        )

        if timeout is None:
            timeout = self._timeout

        try:
            # 发送请求
            await self._socket.send_multipart([
                b"call_from_client",  # 添加消息类型
                method.encode(),  # 服务名称
                serialize_message(request)  # 请求数据
            ])

            # 接收响应流
            while True:
                try:
                    multipart = await asyncio.wait_for(
                        self._socket.recv_multipart(),
                        timeout=timeout
                    )

                    response = deserialize_message(multipart[-1])
                    self._logger.debug(f"Received response type: {type(response)}, content: {response}")

                    if isinstance(response, StreamingBlock):
                        if isinstance(response, EndBlock):
                            return
                        yield response
                    elif isinstance(response, ReplyBlock):
                        yield response.result
                        return
                    elif isinstance(response, ErrorBlock):
                        raise RuntimeError(response.error)
                    else:
                        yield response

                except asyncio.TimeoutError:
                    raise TimeoutError(f"[{self._router_address}] Streaming '{method}' timeout")

        except Exception as e:
            self._logger.error(f"[{self._router_address}] Streaming '{method}' error: {e}")
            raise
