import pytest
import asyncio
import os
import tempfile
from urllib.parse import urlparse

from illufly.mq import Publisher, Subscriber
from illufly.mq.models import StreamingBlock, BlockType

@pytest.mark.asyncio
async def test_ipc_binding():
    """测试 IPC 绑定"""
    # 创建临时 IPC 地址
    with tempfile.NamedTemporaryFile() as tmp:
        ipc_path = f"ipc://{tmp.name}"
        
        # 创建发布者和订阅者
        publisher = Publisher(ipc_path)
        subscriber = Subscriber("test_thread", ipc_path)
        
        messages = []
        collection_task = asyncio.create_task(collect_messages(subscriber, messages))
        
        await asyncio.sleep(0.1)  # 等待连接建立
        publisher.publish("test_thread", "IPC test")
        publisher.end("test_thread")
        
        await collection_task
        
        assert len(messages) == 2
        assert messages[0].content == "IPC test"
        assert messages[1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_tcp_binding():
    """测试 TCP 绑定"""
    tcp_address = "tcp://127.0.0.1:5555"
    
    # 创建发布者和订阅者
    publisher = Publisher(tcp_address)
    subscriber = Subscriber("test_thread", tcp_address)
    
    messages = []
    collection_task = asyncio.create_task(collect_messages(subscriber, messages))
    
    await asyncio.sleep(0.1)
    publisher.publish("test_thread", "TCP test")
    publisher.end("test_thread")
    
    await collection_task
    
    assert len(messages) == 2
    assert messages[0].content == "TCP test"
    assert messages[1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_inproc_binding():
    """测试进程内绑定"""
    inproc_address = "inproc://test"
    
    # 创建发布者和订阅者
    publisher = Publisher(inproc_address)
    subscriber = Subscriber("test_thread", inproc_address)
    
    messages = []
    collection_task = asyncio.create_task(collect_messages(subscriber, messages))
    
    await asyncio.sleep(0.1)
    publisher.publish("test_thread", "Inproc test")
    publisher.end("test_thread")
    
    await collection_task
    
    assert len(messages) == 2
    assert messages[0].content == "Inproc test"
    assert messages[1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_multiple_bindings():
    """测试多个绑定点"""
    addresses = [
        "tcp://127.0.0.1:5556",
        "tcp://127.0.0.1:5557",
    ]
    
    publishers = [Publisher(addr) for addr in addresses]
    subscribers = [Subscriber("test_thread", addr) for addr in addresses]
    
    all_messages = [[] for _ in addresses]
    tasks = [
        asyncio.create_task(collect_messages(sub, msgs))
        for sub, msgs in zip(subscribers, all_messages)
    ]
    
    await asyncio.sleep(0.1)
    
    # 每个发布者发送不同消息
    for i, pub in enumerate(publishers):
        pub.publish("test_thread", f"HistoryMessage from {i}")
        pub.end("test_thread")
    
    await asyncio.gather(*tasks)
    
    # 验证每个订阅者收到对应的消息
    for i, messages in enumerate(all_messages):
        assert len(messages) == 2
        assert messages[0].content == f"HistoryMessage from {i}"
        assert messages[1].block_type == BlockType.END

async def collect_messages(subscriber: Subscriber, messages: list):
    """辅助函数：收集消息"""
    async for msg in subscriber.async_collect():
        messages.append(msg)

def test_invalid_address():
    """测试无效地址"""
    with pytest.raises(Exception):
        Publisher("invalid://address")
    
    with pytest.raises(Exception):
        Subscriber("thread", "invalid://address") 