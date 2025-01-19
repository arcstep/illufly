import pytest
import asyncio
import zmq.asyncio
import os
import multiprocessing
import time
from urllib.parse import urlparse
from illufly.mq.message_bus import MessageBus, BlockType, StreamingBlock

import logging
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_reuse_collector():
    """测试重复使用同一个收集器的情况"""
    bus = MessageBus()
    topic = "test_topic"
    
    try:
        # 确保先订阅
        bus.subscribe(topic)
        await asyncio.sleep(0.1)  # 等待订阅建立
        
        collector = bus.collect()
        
        # 第一次发布和收集
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.CHUNK,
            content="test1"
        ))
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.END
        ))
        
        messages1 = []
        async for msg in collector:  # 使用异步迭代
            messages1.append(msg)
            if msg.block_type == BlockType.END:
                break
                
        assert len(messages1) == 2
        
        # 第二次发布新消息
        collector = bus.collect()  # 重新创建收集器
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.CHUNK,
            content="test2"
        ))
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.END
        ))
        
        messages2 = []
        async for msg in collector:
            messages2.append(msg)
            if msg.block_type == BlockType.END:
                break
                
        assert len(messages2) == 2
        
    finally:
        bus.cleanup()

@pytest.mark.asyncio
async def test_collector_after_end_block():
    """测试在接收到 END 块后继续使用收集器"""
    bus = MessageBus()
    topic = "test_topic"
    
    try:
        bus.subscribe(topic)
        collector = bus.collect()
        
        # 发送消息序列，包括结束标记
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.CHUNK,
            content="test"
        ))
        bus.publish(topic, StreamingBlock(
            block_type=BlockType.END
        ))
        
        # 第一次收集
        messages1 = [msg for msg in collector]
        assert len(messages1) == 2
        assert messages1[-1].block_type == BlockType.END
        
        # 尝试再次收集
        messages2 = [msg for msg in collector]
        assert len(messages2) == 2  # 应该能重复获取缓存的消息
        
    finally:
        bus.cleanup()