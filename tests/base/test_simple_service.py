import pytest
import asyncio
from illufly.base.simple_service import SimpleService
from illufly.mq.models import StreamingBlock, BlockType

class EchoService(SimpleService):
    """简单的回显服务，用于测试"""
    async def _async_handler(self, message: str, *args, thread_id: str, publisher, **kwargs):
        # 模拟一些处理延迟
        await asyncio.sleep(0.1)
        publisher.publish(thread_id, f"Processing: {message}")
        await asyncio.sleep(0.1)
        publisher.publish(thread_id, f"Done: {message}")

class SlowService(SimpleService):
    """模拟慢速处理的服务"""
    async def _async_handler(self, delay: float, *args, thread_id: str, publisher, **kwargs):
        for i in range(3):
            await asyncio.sleep(delay*(i+1))
            publisher.publish(thread_id, f"Step {i+1}")

class ErrorService(SimpleService):
    """模拟错误处理的服务"""
    async def _async_handler(self, *args, thread_id: str, publisher, **kwargs):
        publisher.publish(thread_id, "Starting...")
        await asyncio.sleep(0.1)
        raise ValueError("Simulated error")

@pytest.mark.asyncio
async def test_async_call():
    """测试异步调用"""
    service = EchoService()
    messages = []
    
    async for msg in service.async_call(message="Hello"):
        messages.append(msg)
    
    assert len(messages) == 3  # 2条消息 + END标记
    assert messages[0].content == "Processing: Hello"
    assert messages[1].content == "Done: Hello"
    assert messages[2].block_type == BlockType.END

def test_sync_call():
    """测试同步调用"""
    service = EchoService()
    messages = list(service.call(message="World"))
    
    assert len(messages) == 3
    assert messages[0].content == "Processing: World"
    assert messages[1].content == "Done: World"
    assert messages[2].block_type == BlockType.END

@pytest.mark.asyncio
async def test_timeout():
    """测试超时处理"""
    service = SlowService(timeout=0.5, poll_interval=50)
    messages = []
    
    async for msg in service.async_call(delay=0.3):
        messages.append(msg)
    
    # 由于超时设置为0.5秒，而每步延迟0.3秒，应该只能收到第一条消息和超时错误
    assert len(messages) == 2
    assert messages[0].content == "Step 1"
    assert messages[1].block_type == BlockType.ERROR
    assert "timeout" in messages[1].content.lower()

@pytest.mark.asyncio
async def test_error_handling():
    """测试错误处理"""
    service = ErrorService()
    messages = []
    
    async for msg in service.async_call():
        messages.append(msg)
    
    assert len(messages) == 3
    assert messages[0].content == "Starting..."
    assert messages[1].block_type == BlockType.ERROR
    assert "Simulated error" in messages[1].content
    assert messages[2].block_type == BlockType.END

@pytest.mark.asyncio
async def test_custom_thread_id():
    """测试自定义线程ID"""
    service = EchoService()
    custom_id = "test_thread_123"
    messages = []
    
    async for msg in service.async_call(message="Test", thread_id=custom_id):
        messages.append(msg)
    
    assert len(messages) == 3
    assert messages[0].content == "Processing: Test"
    assert messages[1].content == "Done: Test"

@pytest.mark.asyncio
async def test_multiple_calls():
    """测试多次调用"""
    service = EchoService()
    
    # 第一次调用
    messages1 = []
    async for msg in service.async_call(message="First"):
        messages1.append(msg)
    
    # 第二次调用
    messages2 = []
    async for msg in service.async_call(message="Second"):
        messages2.append(msg)
    
    assert len(messages1) == 3
    assert len(messages2) == 3
    assert messages1[0].content == "Processing: First"
    assert messages2[0].content == "Processing: Second"

@pytest.mark.asyncio
async def test_custom_addresses():
    """测试自定义地址"""
    service = EchoService(
        address="tcp://127.0.0.1:5555",
    )
    messages = []
    
    async for msg in service.async_call(message="Custom"):
        messages.append(msg)
    
    assert len(messages) == 3
    assert messages[0].content == "Processing: Custom"
    assert messages[1].content == "Done: Custom" 