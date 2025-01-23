from typing import Optional, Dict, Any, List

from ..models import RequestBlock, ReplyBlock, ReplyState, ReplyReadyBlock, ReplyAcceptedBlock, RequestStep
from ..base_mq import BaseMQ
from ..pubsub import Subscriber

import zmq

class Requester(BaseMQ):
    """ZMQ REQ 请求者"""
    def __init__(self, address=None, logger=None, timeout: int=10*1000):
        super().__init__(address, logger)
        self._timeout = timeout
        self.to_connecting()

    def to_connecting(self):
        """初始化请求socket"""
        try:
            self._connected_socket = self._context.socket(zmq.REQ)
            self._connected_socket.setsockopt(zmq.RCVTIMEO, self._timeout)
            self._connected_socket.connect(self._address)
            self._logger.info(f"Requester connected to: {self._address}")
        except Exception as e:
            self._logger.error(f"Connection error: {e}")
            raise

    async def async_request(self, args: List[Any] = [], kwargs: Dict[str, Any] = {}, thread_id: str = "") -> Optional[Subscriber]:
        """发送请求并等待响应"""
        if not self._connected_socket:
            raise RuntimeError("Requester not connected")

        try:
            # STEP 1: 发送请求
            request = RequestBlock(
                thread_id=thread_id,
                request_step=RequestStep.INIT,
            )
            await self._connected_socket.send_json(request.model_dump())

            # STEP 2: 等待服务端确认，并获得 thread_id 和 subscribe_address
            reply_data = await self._connected_socket.recv_json()
            self._logger.debug(f"Client received accepted reply: {reply_data}")
            if reply_data.get("state") == ReplyState.ERROR.value:
                raise Exception(reply_data.get("error"))

            accepted_block = ReplyAcceptedBlock.model_validate(reply_data)

            # STEP 3: 根据上面后的关键信息创建订阅
            sub = Subscriber(
                thread_id=accepted_block.thread_id,
                address=accepted_block.subscribe_address,
                timeout=self._timeout
            )

            # STEP 4: 订阅准备已就绪
            ready = RequestBlock(
                thread_id=accepted_block.thread_id,
                request_step=RequestStep.READY,
                args=args,
                kwargs=kwargs
            )
            await self._connected_socket.send_json(ready.model_dump())
            self._logger.debug(f"Client sent ready reply: {ready}")

            # STEP 5: 等待异步处理完成
            processing_data = await self._connected_socket.recv_json()
            if processing_data.get("state") == ReplyState.ERROR.value:
                raise Exception(reply_data.get("error"))

            return sub

        except Exception as e:
            self._logger.error(f"Request failed: {e}")
            raise

    def request(self, args: List[Any] = [], kwargs: Dict[str, Any] = {}) -> Optional[ReplyBlock]:
        """同步请求"""
        return self._async_utils.wrap_async_func(self.async_request)(args, kwargs)

    def cleanup(self):
        """清理资源"""
        if self._connected_socket:
            self._connected_socket.close()
            self._connected_socket = None
            self._logger.debug("Requester socket closed")
