import pytest
import asyncio
import logging
from illufly.base.base_service import BaseService
from illufly.mq.models import StreamingBlock, BlockType

logger = logging.getLogger(__name__)

class MyService(BaseService):
    """用于测试的服务类"""
    def __init__(self, response="test", sleep=0.01, **kwargs):
        super().__init__(**kwargs)
        self.response = response
        self.sleep = sleep
        self.register_method("server", async_handle=self._test_handler)
        
    async def _test_handler(self, message: str, thread_id: str, message_bus):
        """测试处理器"""
        # 发送开始消息
        message_bus.publish(thread_id, StreamingBlock(
            block_type=BlockType.START,
            content="start",
            topic=thread_id
            ))
        
        # 发送响应内容
        await asyncio.sleep(self.sleep)
        message_bus.publish(thread_id, StreamingBlock(
            block_type=BlockType.CHUNK,
            content=message,
            topic=thread_id
        ))

class TestBaseServiceResponse:
    """测试 BaseService 的响应处理"""
    
    def test_sync_response_auto_close(self):
        """测试同步响应"""
        service = MyService()
        response = service.call("test")
        
        # 部分消费消息
        messages = []
        for msg in response:
            messages.append(msg)
        assert len(messages) == 3
                
    @pytest.mark.asyncio
    async def test_async_response_auto_close(self):
        """测试异步响应"""
        service = MyService()
        response = await service.async_call("test")
        
        # 部分消费消息
        messages = []
        async for msg in response:
            messages.append(msg)

        assert len(messages) == 3