import pytest
import asyncio
import time
import logging

from illufly.mq.pub import Publisher, DEFAULT_PUBLISHER
from illufly.mq.sub import Subscriber
from illufly.mq.models import StreamingBlock, BlockType

logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_mq(caplog):
    caplog.set_level(logging.INFO)

@pytest.mark.asyncio
async def test_streaming_collection():
    """测试流式收集消息"""
    publisher = DEFAULT_PUBLISHER
    subscriber = Subscriber("test_stream")
    
    received_times = []
    
    async def delayed_publish():
        """延迟发布消息"""
        for i in range(3):
            await asyncio.sleep(0.1)  # 模拟消息间隔
            publisher.publish("test_stream", f"message {i}")
            if i < 2:  # 只在非最后一条消息后等待
                await asyncio.sleep(0.1)
        publisher.end("test_stream")
    
    async def collect_with_timing():
        async for msg in subscriber.async_collect():
            if msg.block_type != BlockType.END:  # 只记录非END消息的时间
                received_times.append(time.time())
            yield msg
    
    # 同时启动发布和收集
    publish_task = asyncio.create_task(delayed_publish())
    messages = []
    
    async for msg in collect_with_timing():
        messages.append(msg)
    
    await publish_task
    
    # 验证消息内容
    assert len(messages) == 4  # 3条消息 + 1条END标记
    assert [msg.content for msg in messages[:-1]] == [
        "message 0",
        "message 1",
        "message 2"
    ]
    assert messages[-1].block_type == BlockType.END
    
    # 验证消息是流式接收的（只检查实际消息的间隔）
    time_intervals = [received_times[i+1] - received_times[i] 
                     for i in range(len(received_times)-1)]
    logger.info(f"Time intervals: {time_intervals}")
    assert all(interval >= 0.08 for interval in time_intervals)  # 考虑一些误差

@pytest.mark.asyncio
async def test_streaming_with_timeout():
    """测试带超时的流式处理"""
    publisher = DEFAULT_PUBLISHER
    subscriber = Subscriber("timeout_stream")
    
    received_messages = []
    received_times = []
    
    async def delayed_publish():
        """延迟发布消息，包含一个较长的间隔"""
        publisher.publish("timeout_stream", "message 1")
        await asyncio.sleep(0.1)
        publisher.publish("timeout_stream", "message 2")
        await asyncio.sleep(0.5)  # 超过超时时间
        publisher.publish("timeout_stream", "message 3")  # 这条消息不应该被接收
        publisher.end("timeout_stream")
    
    publish_task = asyncio.create_task(delayed_publish())
    
    # 设置较短的超时时间
    async for msg in subscriber.async_collect(timeout=0.3):
        received_messages.append(msg)
        received_times.append(time.time())
    
    await publish_task
    
    # 验证只收到前两条消息和超时错误
    assert len(received_messages) == 3
    assert received_messages[0].content == "message 1"
    assert received_messages[1].content == "message 2"
    assert received_messages[2].block_type == BlockType.ERROR
    assert "timeout" in received_messages[2].content.lower()

@pytest.mark.asyncio
async def test_streaming_cancellation():
    """测试流式处理的取消操作"""
    publisher = DEFAULT_PUBLISHER
    subscriber = Subscriber("cancel_stream")
    
    received_messages = []
    
    async def delayed_publish():
        for i in range(5):
            await asyncio.sleep(0.1)
            publisher.publish("cancel_stream", f"message {i}")
        publisher.end("cancel_stream")
    
    publish_task = asyncio.create_task(delayed_publish())
    collection_task = asyncio.create_task(collect_messages(subscriber, received_messages))
    
    # 等待接收部分消息后取消
    await asyncio.sleep(0.25)
    collection_task.cancel()
    
    try:
        await collection_task
    except asyncio.CancelledError:
        pass
    
    await publish_task
    
    # 验证只收到部分消息
    assert 1 <= len(received_messages) <= 3  # 考虑时间误差
    assert all(msg.content.startswith("message") for msg in received_messages)

async def collect_messages(subscriber: Subscriber, messages: list):
    """辅助函数：收集消息"""
    async for msg in subscriber.async_collect():
        messages.append(msg)

@pytest.mark.asyncio
async def test_streaming_reuse():
    """测试流式处理后的重用"""
    publisher = DEFAULT_PUBLISHER
    subscriber = Subscriber("reuse_stream")
    
    # 第一次收集 - 流式处理
    first_messages = []
    async def delayed_publish():
        for i in range(3):
            await asyncio.sleep(0.1)
            publisher.publish("reuse_stream", f"message {i}")
        publisher.end("reuse_stream")
    
    publish_task = asyncio.create_task(delayed_publish())
    async for msg in subscriber.async_collect():
        first_messages.append(msg)
    await publish_task
    
    # 第二次收集 - 应该立即从缓存返回
    second_messages = []
    start_time = time.time()
    async for msg in subscriber.async_collect():
        second_messages.append(msg)
    collection_time = time.time() - start_time
    
    # 验证结果
    assert first_messages == second_messages
    assert len(first_messages) == 4  # 3条消息 + END
    assert collection_time < 0.1  # 从缓存读取应该很快 