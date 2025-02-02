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
        
        self._context = context or zmq.asyncio.Context()
        self._socket = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def _ensure_connected(self):
        """确保连接已建立，如果没有则建立连接"""
        if not self._connected:
            async with self._lock:
                if not self._connected:  # 双重检查
                    if not self._socket:
                        self._socket = self._context.socket(zmq.DEALER)
                        self._socket.set_hwm(self._hwm)
                    self._socket.connect(self._router_address)
                    self._connected = True
                    self._logger.debug(f"Connected to router at {self._router_address}")

    async def close(self):
        """关闭连接"""
        if self._socket:
            self._socket.close()
            self._socket = None
        self._connected = False

    @asynccontextmanager
    async def connection(self):
        """连接上下文管理器"""
        try:
            await self._ensure_connected()
            yield self
        except Exception as e:
            self._logger.error(f"Connection error: {e}")
            await self.close()
            raise

    async def discover_services(self, timeout: Optional[float] = None) -> Dict[str, Dict]:
        """发现可用的服务及其方法"""
        if timeout is None:
            timeout = self._timeout

        async with self.connection():
            try:
                # 修改发送格式以匹配Router期望
                await self._socket.send_multipart([
                    b"discovery",  # message_type
                    b""  # empty content
                ])

                # 等待响应
                multipart = await asyncio.wait_for(
                    self._socket.recv_multipart(),
                    timeout=timeout
                )

                response = deserialize_message(multipart[0])
                self._logger.debug(f"Received discovery response: {response}")

                if isinstance(response, ReplyBlock):
                    return response.result  # 直接返回 result 字段
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
                # 先检查服务是否存在
                services = await self.discover_services(timeout=timeout)
                service_found = False
                for service_info in services.values():
                    if service_name in service_info:
                        service_found = True
                        break
                
                if not service_found:
                    raise RuntimeError(f"Service method '{service_name}' not found. Available services: {[method for service in services.values() for method in service.keys()]}")

                # 发送请求
                await self._socket.send_multipart([
                    service_name.encode(),
                    serialize_message(request)
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

    def _serialize_message(self, message: Any) -> bytes:
        """序列化消息"""
        if hasattr(message, 'model_dump_json'):
            return message.model_dump_json().encode()
        return json.dumps(message).encode()

    def _deserialize_message(self, data: bytes) -> Any:
        """反序列化消息"""
        return json.loads(data.decode())