import pytest
import asyncio
import logging
from illufly.base import LocalService
from illufly.mq.models import StreamingBlock, BlockType

logger = logging.getLogger(__name__)

class MyService(LocalService):
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

class TestLocalServiceResponse:
    """测试 LocalService 的响应处理"""
    
    def test_sync_response_auto_close(self):
        """测试同步响应"""
        service = MyService()
        response = service.call("test")
        
        # 部分消费消息
        messages = []
        for msg in response:
            messages.append(msg)
        assert len(messages) == 3

    def test_sync_response_recollect(self):
        """重复收集"""
        service = MyService()
        response = service.call("test")
        
        # 部分消费消息
        messages = []
        for msg in response:
            messages.append(msg)
        assert len(messages) == 3

        messages2 = []
        for msg in response:
            messages2.append(msg)
        assert len(messages2) == 3

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

    @pytest.mark.asyncio
    async def test_async_response_recollect(self):
        """测试异步响应"""
        service = MyService()
        response = await service.async_call("test")
        
        # 部分消费消息
        messages = []
        async for msg in response:
            messages.append(msg)

        assert len(messages) == 3

        messages2 = []
        async for msg in response:
            messages2.append(msg)
        assert len(messages2) == 3

class MyServiceWithError(LocalService):
    """用于测试的服务类"""
    def __init__(self, response="test", sleep=0.01, **kwargs):
        super().__init__(**kwargs)
        self.response = response
        self.sleep = sleep
        self.register_method("server", async_handle=self._test_handler)
        
    async def _test_handler(self, message: str, thread_id: str, message_bus):
        """测试处理器"""
        raise ValueError("Test error")

class TestLocalServiceException:
    """测试 LocalService 的异常处理"""
    
    @pytest.fixture
    def error_service(self):
        """创建一个包含错误处理器的服务"""
        return MyServiceWithError(service_name="test_exception")

    def test_exception_with_end_block(self, error_service):
        """测试异常情况下是否正确发送结束标记"""
        blocks = []
        
        # 收集消息
        for block in error_service.call("test_error"):
            blocks.append(block)
        
        # 验证是否收到了错误块和结束标记
        assert len(blocks) >= 2
        assert any(block.block_type == BlockType.ERROR for block in blocks)
        assert blocks[-1].block_type == BlockType.END

    def test_multiple_exceptions(self, error_service):
        """测试连续异常调用的情况"""
        for _ in range(3):
            blocks = []
            for block in error_service.call("error_handler"):
                blocks.append(block)
            
            # 每次调用都应该收到结束标记
            assert blocks[-1].block_type == BlockType.END

    def test_exception_message_content(self, error_service):
        """测试异常消息的内容是否正确"""
        blocks = []
        for block in error_service.call("error_handler"):
            blocks.append(block)
        
        # 验证错误块的内容
        error_blocks = [b for b in blocks if b.block_type == BlockType.ERROR]
        assert len(error_blocks) == 1
        assert "Test error" in error_blocks[0].content