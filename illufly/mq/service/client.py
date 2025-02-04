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
    EndBlock, ErrorBlock, RequestStep, TextFinal, BlockType
)
from .utils import serialize_message, deserialize_message

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
        self._client_id = str(uuid.uuid4())
        self._available_methods = {}  # 缓存可用方法

    async def _connect(self):
        """连接到路由器"""
        if not self._socket:
            self._socket = self._context.socket(zmq.DEALER)
            self._socket.identity = self._client_id.encode()
            self._socket.set_hwm(self._hwm)
            self._socket.connect(self._router_address)
            self._connected = True
            # 连接后立即更新可用方法
            await self.discover_services()
            self._logger.debug(f"Connected to router at {self._router_address}")

    async def close(self):
        """关闭连接"""
        self._available_methods = {}
        if self._socket:
            self._socket.close()
            self._socket = None
        self._connected = False

    @asynccontextmanager
    async def connection(self):
        """连接上下文管理器"""
        try:
            await self._connect()
            yield self
        except Exception as e:
            self._logger.error(f"Connection error: {e}")
            await self.close()
            raise

    async def discover_services(self, timeout: Optional[float] = None) -> Dict[str, Dict]:
        """发现可用的服务方法
        
        Returns:
            Dict[str, Dict]: 方法名到方法信息的映射
            例如：{
                "echo": {},
                "add": {
                    "description": "Add two numbers",
                    "params": {
                        "a": "first number",
                        "b": "second number"
                    }
                }
            }
        """
        if timeout is None:
            timeout = self._timeout
        
        try:
            await self._socket.send_multipart([
                b"discovery",
                b""
            ])

            multipart = await asyncio.wait_for(
                self._socket.recv_multipart(),
                timeout=timeout
            )

            response = deserialize_message(multipart[-1])
            self._logger.debug(f"Received discovery response: {response}")

            if isinstance(response, ReplyBlock):
                self._available_methods = response.result
                return self._available_methods
            elif isinstance(response, ErrorBlock):
                raise RuntimeError(response.error)
            else:
                raise ValueError(f"Unexpected response type: {type(response)}")

        except asyncio.TimeoutError:
            raise TimeoutError("Service discovery timeout")
        except Exception as e:
            self._logger.error(f"Service discovery error: {e}")
            raise

    async def call_service(
        self,
        service_name: str,
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        """调用服务，返回异步生成器"""
        if not self._connected:
            await self._connect()

        if service_name not in self._available_methods:
            # 如果方法不在缓存中，尝试更新一次
            await self.discover_services()
            if service_name not in self._available_methods:
                raise RuntimeError(
                    f"Service method '{service_name}' not found. "
                    f"Available methods: {list(self._available_methods.keys())}"
                )

        request_id = str(uuid.uuid4())
        request = RequestBlock(
            request_id=request_id,
            func_name=service_name,
            request_step=RequestStep.READY,
            args=args,
            kwargs=kwargs
        )

        if timeout is None:
            timeout = self._timeout

        async with self.connection():
            try:
                # 发送请求
                await self._socket.send_multipart([
                    b"call",  # 添加消息类型
                    service_name.encode(),  # 服务名称
                    serialize_message(request)  # 请求数据
                ])

                # 接收响应流
                while True:
                    try:
                        self._logger.debug(f"Waiting for response: {request_id}")
                        multipart = await asyncio.wait_for(
                            self._socket.recv_multipart(),
                            timeout=timeout
                        )

                        response = deserialize_message(multipart[-1])
                        self._logger.debug(f"Received response type: {type(response)}, content: {response}")

                        if isinstance(response, StreamingBlock):
                            if isinstance(response, EndBlock):
                                return
                            yield response.content
                        elif isinstance(response, ReplyBlock):
                            yield response.result
                            return
                        elif isinstance(response, ErrorBlock):
                            raise RuntimeError(response.error)
                        else:
                            yield response

                    except asyncio.TimeoutError:
                        raise TimeoutError(f"Service call timeout: {service_name}")

            except Exception as e:
                self._logger.error(f"Service call error: {e}")
                raise
