import pytest
import asyncio
from illufly.mq.pub import Publisher, DEFAULT_PUBLISHER
from illufly.mq.sub import Subscriber
from illufly.mq.models import StreamingBlock, BlockType

async def collect_messages(subscriber: Subscriber, messages: list):
    """辅助函数：收集消息"""
    async for msg in subscriber.async_collect():
        messages.append(msg)

@pytest.mark.asyncio
async def test_basic_pubsub():
    """测试基本的发布订阅功能"""
    # 创建订阅者
    subscriber = Subscriber("test_topic")
    
    # 使用默认发布者
    messages = []
    collection_task = asyncio.create_task(collect_messages(subscriber, messages))
    
    # 发送消息
    await asyncio.sleep(0.1)  # 确保订阅已建立
    DEFAULT_PUBLISHER.publish("test_topic", "Hello")
    DEFAULT_PUBLISHER.publish("test_topic", "World")
    DEFAULT_PUBLISHER.end("test_topic")
    
    # 等待收集完成
    await collection_task
    
    # 验证结果
    assert len(messages) == 3
    assert messages[0].content == "Hello"
    assert messages[1].content == "World"
    assert messages[2].block_type == BlockType.END

@pytest.mark.asyncio
async def test_multiple_subscribers():
    """测试多个订阅者"""
    sub1 = Subscriber("topic1")
    sub2 = Subscriber("topic2")
    
    messages1, messages2 = [], []
    task1 = asyncio.create_task(collect_messages(sub1, messages1))
    task2 = asyncio.create_task(collect_messages(sub2, messages2))
    
    await asyncio.sleep(0.1)
    
    # 发送到不同主题
    DEFAULT_PUBLISHER.publish("topic1", "Message for 1")
    DEFAULT_PUBLISHER.publish("topic2", "Message for 2")
    DEFAULT_PUBLISHER.end("topic1")
    DEFAULT_PUBLISHER.end("topic2")
    
    await asyncio.gather(task1, task2)
    
    assert len(messages1) == 2
    assert len(messages2) == 2
    assert messages1[0].content == "Message for 1"
    assert messages2[0].content == "Message for 2"

@pytest.mark.asyncio
async def test_subscriber_timeout():
    """测试订阅者超时"""
    subscriber = Subscriber("timeout_topic", timeout=0.5)
    messages = []
    
    # 设置较短的超时时间
    async for msg in subscriber.async_collect():
        messages.append(msg)
    
    assert len(messages) == 1
    assert messages[0].block_type == BlockType.ERROR
    assert "timeout" in messages[0].content.lower()

@pytest.mark.asyncio
async def test_subscriber_reuse():
    """测试订阅者重用缓存"""
    subscriber = Subscriber("reuse_topic")
    
    # 第一次收集
    messages1 = []
    collection_task = asyncio.create_task(collect_messages(subscriber, messages1))
    
    await asyncio.sleep(0.1)
    DEFAULT_PUBLISHER.publish("reuse_topic", "Test message")
    DEFAULT_PUBLISHER.end("reuse_topic")
    
    await collection_task
    
    # 第二次收集（应该从缓存获取）
    messages2 = []
    async for msg in subscriber.async_collect():
        messages2.append(msg)
    
    assert messages1 == messages2
    assert len(messages1) == 2

@pytest.mark.asyncio
async def test_custom_publisher():
    """测试自定义发布者"""
    publisher = Publisher("inproc://custom_test")
    subscriber = Subscriber("test_topic", "inproc://custom_test")
    
    messages = []
    collection_task = asyncio.create_task(collect_messages(subscriber, messages))
    
    await asyncio.sleep(0.1)
    publisher.publish("test_topic", "Custom message")
    publisher.end("test_topic")
    
    await collection_task
    
    assert len(messages) == 2
    assert messages[0].content == "Custom message"
    assert messages[1].block_type == BlockType.END 