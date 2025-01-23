import asyncio
from zmq.devices import Device
import zmq.asyncio

from ..base_mq import BaseMQ

class RouterDevice(BaseMQ):
    """路由设备，用于转发请求到多个 Replier"""
    
    def __init__(self, frontend_address: str, backend_address: str, logger=None):
        super().__init__(address=None, logger=logger)
        self._frontend_address = frontend_address
        self._backend_address = backend_address
        self._frontend = None
        self._backend = None
        self.running = False  # 添加运行状态标志
        
    def _init_sockets(self):
        """初始化前端和后端socket"""
        self._frontend = self._context.socket(zmq.ROUTER)
        self._backend = self._context.socket(zmq.DEALER)
        
        # 设置高水位标记，确保与 Replier 的设置匹配
        hwm = self._max_concurrent_tasks * 2 if hasattr(self, '_max_concurrent_tasks') else 1000
        self._frontend.set_hwm(hwm)
        self._backend.set_hwm(hwm)
        
        # 绑定前端地址（面向客户端）
        self._frontend.bind(self._frontend_address)
        # 绑定后端地址（面向 Replier）
        self._backend.bind(self._backend_address)
        
        self._logger.info(f"Router device initialized: {self._frontend_address} -> {self._backend_address}")

    async def start(self):
        """启动路由设备"""
        self._init_sockets()
        self.running = True
        try:
            self._logger.info("Starting router device...")
            await self._route_messages()
        finally:
            self.running = False
            self.cleanup()

    async def _route_messages(self):
        """消息路由主循环"""
        try:
            while True:
                # 使用 zmq.asyncio.Poller 进行消息轮询
                poller = zmq.asyncio.Poller()
                poller.register(self._frontend, zmq.POLLIN)
                poller.register(self._backend, zmq.POLLIN)
                
                events = dict(await poller.poll())
                
                # 处理前端（客户端）消息
                if self._frontend in events:
                    message = await self._frontend.recv_multipart()
                    self._logger.debug(f"Frontend received: {len(message)} parts")
                    await self._backend.send_multipart(message)
                
                # 处理后端（Replier）消息
                if self._backend in events:
                    message = await self._backend.recv_multipart()
                    self._logger.debug(f"Backend received: {len(message)} parts")
                    await self._frontend.send_multipart(message)
                    
        except asyncio.CancelledError:
            self._logger.info("Router device stopping...")
            raise
        except Exception as e:
            self._logger.error(f"Router error: {e}")
            raise

    def cleanup(self):
        """清理资源"""
        if self._frontend:
            self._frontend.close()
        if self._backend:
            self._backend.close()
        self._logger.info("Router device cleaned up")