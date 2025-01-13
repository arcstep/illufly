import pytest
import asyncio
import zmq.asyncio
import os
import multiprocessing
import time
from urllib.parse import urlparse
from illufly.mq.message_bus import MessageBus

import logging
logger = logging.getLogger(__name__)

class TestPubSubFunctionality:
    """发布订阅功能测试
    
    设计意图：
    1. 验证主题过滤的准确性
    2. 确保消息顺序和完整性
    3. 测试多发布者/订阅者场景
    4. 验证高负载下的性能表现
    """
    
    @pytest.mark.asyncio
    async def test_pub_sub_inproc(self):
        """测试进程内发布订阅"""
        bus1 = MessageBus(logger=logger)
        bus2 = MessageBus(logger=logger)
        received = []
        
        try:
            # 等待连接建立
            await asyncio.sleep(0.1)
            
            async def subscriber():
                async with asyncio.timeout(1.0):
                    async for msg in bus2.subscribe(["test"]):
                        logger.debug(f"Subscriber received: {msg}")
                        received.append(msg)
                        if len(received) >= 2:
                            break
            
            # 启动订阅任务
            sub_task = asyncio.create_task(subscriber())
            # 等待订阅建立
            await asyncio.sleep(0.1)
            
            logger.debug("Starting to publish messages")
            # 发送多条消息
            bus1.publish("test", {"msg": "hello1"})
            bus1.publish("test", {"msg": "hello2"})
            
            await sub_task
            assert len(received) == 2
            assert received[0]["msg"] == "hello1"
            assert received[1]["msg"] == "hello2"
            
        finally:
            bus1.cleanup()
            bus2.cleanup()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """测试多个订阅者"""
        bus_pub = MessageBus(logger=logger)
        bus_sub1 = MessageBus(logger=logger)
        bus_sub2 = MessageBus(logger=logger)
        received1 = []
        received2 = []
        
        try:
            # 等待连接建立
            await asyncio.sleep(0.1)
            
            async def subscriber1():
                async with asyncio.timeout(1.0):
                    async for msg in bus_sub1.subscribe(["test"]):
                        received1.append(msg)
                        break
                        
            async def subscriber2():
                async with asyncio.timeout(1.0):
                    async for msg in bus_sub2.subscribe(["test"]):
                        received2.append(msg)
                        break
            
            sub_task1 = asyncio.create_task(subscriber1())
            sub_task2 = asyncio.create_task(subscriber2())
            await asyncio.sleep(0.1)
            
            bus_pub.publish("test", {"msg": "hello"})
            
            await asyncio.gather(sub_task1, sub_task2)
            assert received1[0]["msg"] == "hello"
            assert received2[0]["msg"] == "hello"
            
        finally:
            bus_pub.cleanup()
            bus_sub1.cleanup()
            bus_sub2.cleanup()

    @pytest.mark.asyncio
    async def test_topic_filtering(self):
        """测试主题过滤"""
        bus1 = MessageBus(logger=logger)
        bus2 = MessageBus(logger=logger)
        received = []
        
        try:
            
            # 等待连接建立
            await asyncio.sleep(0.1)
            
            async def subscriber():
                async with asyncio.timeout(1.0):
                    async for msg in bus2.subscribe(["topic1"]):
                        received.append(msg)
                        break
            
            sub_task = asyncio.create_task(subscriber())
            await asyncio.sleep(0.1)
            
            # 发送到不同主题
            bus1.publish("topic1", {"msg": "hello1"})
            bus1.publish("topic2", {"msg": "hello2"})
            
            await sub_task
            assert len(received) == 1
            assert received[0]["msg"] == "hello1"
            
        finally:
            bus1.cleanup()
            bus2.cleanup()

    @pytest.mark.asyncio
    async def test_high_load_pub_sub(self):
        """测试高负载场景
        
        验证在大量消息和多个订阅者的情况下：
        1. 消息不丢失
        2. 顺序保持正确
        3. 系统保持稳定
        """
        bus_pub = MessageBus(logger=logger)
        bus_sub1 = MessageBus(logger=logger)
        bus_sub2 = MessageBus(logger=logger)
        received1 = []
        received2 = []
        
        MSG_COUNT = 1000  # 每个主题发送1000条消息
        TOPICS = ["topic1", "topic2"]  # 测试多个主题
        
        try:
            await asyncio.sleep(0.1)
            
            async def subscriber(bus, received, expected_count):
                async with asyncio.timeout(5.0):  # 增加超时时间
                    async for msg in bus.subscribe(TOPICS):
                        received.append(msg)
                        if len(received) >= expected_count:
                            break
            
            # 启动订阅者
            sub_task1 = asyncio.create_task(
                subscriber(bus_sub1, received1, MSG_COUNT * len(TOPICS))
            )
            sub_task2 = asyncio.create_task(
                subscriber(bus_sub2, received2, MSG_COUNT * len(TOPICS))
            )
            await asyncio.sleep(0.5)
            
            # 高速发布消息
            start_time = time.time()
            for topic in TOPICS:
                for i in range(MSG_COUNT):
                    bus_pub.publish(topic, {
                        "seq": i,
                        "topic": topic,
                        "msg": f"message-{i}"
                    })
            
            # 等待所有消息接收完成
            await asyncio.gather(sub_task1, sub_task2)
            elapsed = time.time() - start_time
            
            # 验证结果
            for received in [received1, received2]:
                # 检查消息数量
                assert len(received) == MSG_COUNT * len(TOPICS)
                
                # 检查每个主题的消息顺序
                for topic in TOPICS:
                    topic_msgs = [msg for msg in received if msg["topic"] == topic]
                    assert len(topic_msgs) == MSG_COUNT
                    sequences = [msg["seq"] for msg in topic_msgs]
                    assert sequences == list(range(MSG_COUNT))
            
            # 记录性能指标
            total_msgs = MSG_COUNT * len(TOPICS) * 2  # 2个订阅者
            msg_per_sec = total_msgs / elapsed
            logger.info(f"Processed {total_msgs} messages in {elapsed:.2f} seconds")
            logger.info(f"Average throughput: {msg_per_sec:.2f} messages/second")
            
        finally:
            bus_pub.cleanup()
            bus_sub1.cleanup()
            bus_sub2.cleanup() 
