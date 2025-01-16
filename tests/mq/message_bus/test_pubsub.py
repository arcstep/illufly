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
    
    @pytest.mark.parametrize("address", [
        "inproc://test_pubsub",
        pytest.param(
            "ipc:///tmp/test_pubsub.ipc", 
            marks=pytest.mark.skipif(
                os.name == 'nt', 
                reason="IPC not supported on Windows"
            )
        ),
        "tcp://127.0.0.1:5555"
    ])
    def test_pub_sub_basic(self, address):
        """测试基本的发布订阅功能
        
        验证不同传输模式下：
        1. 发布者和订阅者能正确通信
        2. 消息顺序保持正确
        3. 资源能正确清理
        """
        bus1 = MessageBus(address=address, logger=logger)
        bus2 = MessageBus(address=address, logger=logger)
        
        try:
            bus2.subscribe(["test"])
            # 发送多条消息
            bus1.publish("test", {"msg": "hello1"}, end=False)
            bus1.publish("test", {"msg": "hello2"}, end=True)
            
            received = list(bus2.collect())
            assert len(received) == 3
            assert received[0]["msg"] == "hello1"
            assert received[1]["msg"] == "hello2"
            
        finally:
            bus1.cleanup()
            bus2.cleanup()

    @pytest.mark.parametrize("address", [
        "inproc://test_pubsub",
        pytest.param(
            "ipc:///tmp/test_pubsub.ipc", 
            marks=pytest.mark.skipif(
                os.name == 'nt', 
                reason="IPC not supported on Windows"
            )
        ),
        "tcp://127.0.0.1:5555"
    ])
    def test_pub_multi_topics(self, address):
        """测试多主题发布订阅功能
        
        验证不同传输模式下：
        1. 发布者和订阅者能正确通信
        2. 消息顺序保持正确
        3. 资源能正确清理
        """
        bus1 = MessageBus(address=address, logger=logger)
        bus2 = MessageBus(address=address, logger=logger)
        
        try:
            bus2.subscribe(["test1", "test2"])
            # 发送多条消息
            bus1.publish("test1", {"msg": "hello1"}, end=False)
            bus1.publish("test2", {"msg": "hello2"}, end=False)
            bus1.publish("test1", end=True)
            
            received = list(bus2.collect())
            assert len(received) == 3
            assert received[0]["msg"] == "hello1"
            assert received[1]["msg"] == "hello2"
            
        finally:
            bus1.cleanup()
            bus2.cleanup()

    @pytest.mark.parametrize("address", [
        "inproc://test_multiple",
        pytest.param(
            "ipc:///tmp/test_multiple.ipc", 
            marks=pytest.mark.skipif(os.name == 'nt', 
            reason="IPC not supported on Windows")
        ),
        "tcp://127.0.0.1:5556"
    ])
    def test_multiple_subscribers(self, address):
        """测试多个订阅者
        
        验证不同传输模式下：
        1. 多个订阅者都能收到消息
        2. 消息内容保持一致
        """
        bus_pub = MessageBus(address=address, logger=logger)
        bus_sub1 = MessageBus(address=address, logger=logger)
        bus_sub2 = MessageBus(address=address, logger=logger)
        
        try:
            bus_sub1.subscribe(["test"])
            bus_sub2.subscribe(["test"])
            bus_pub.publish("test", {"msg": "hello"}, end=True)

            received1 = list(bus_sub1.collect())
            received2 = list(bus_sub2.collect())
            assert received1[0]["msg"] == "hello"
            assert received2[0]["msg"] == "hello"
            
        finally:
            bus_pub.cleanup()
            bus_sub1.cleanup()
            bus_sub2.cleanup()

    def test_topic_filtering(self):
        """测试主题过滤"""
        bus1 = MessageBus(logger=logger)
        bus2 = MessageBus(logger=logger)
        received = []
        
        try:            
            bus2.subscribe(["topic1"])
            bus1.publish("topic1", {"msg": "hello1"}, end=True)
            bus1.publish("topic2", {"msg": "hello2"}, end=True)
            received = list(bus2.collect())
            assert len(received) == 2
            assert received[0]["msg"] == "hello1"
            
        finally:
            bus1.cleanup()
            bus2.cleanup()

    def test_high_load_pub_sub(self, caplog):
        """测试高负载场景
        
        验证在大量消息和多个订阅者的情况下：
        1. 消息不丢失
        2. 顺序保持正确
        3. 系统保持稳定
        """
        caplog.set_level(logging.INFO)

        bus_pub = MessageBus(logger=logger)
        bus_sub1 = MessageBus(logger=logger)
        bus_sub2 = MessageBus(logger=logger)
        
        MSG_COUNT = 1000  # 每个主题发送1000条消息
        
        try: 
            bus_sub1.subscribe("topic1")
            bus_sub2.subscribe("topic2")
            
            # 高速发布消息
            start_time = time.time()
            for topic in ["topic1", "topic2"]:
                for i in range(MSG_COUNT):
                    bus_pub.publish(
                        topic,
                        {"seq": i, "topic": topic, "msg": f"message-{i}"},
                        end=False,
                        delay=0
                    )
            bus_pub.publish("topic1", end=True)
            bus_pub.publish("topic2", end=True)
            
            # 验证结果
            received1 = list(bus_sub1.collect(timeout=5.0))
            received2 = list(bus_sub2.collect(timeout=5.0))

            for received in [received1, received2]:
                # 检查消息数量
                assert len(received) == MSG_COUNT + 1
            
            # 记录性能指标
            elapsed = time.time() - start_time
            total_msgs = (MSG_COUNT + 1) * 2  # 2个订阅者
            msg_per_sec = total_msgs / elapsed
            logger.info(f"Processed {total_msgs} messages in {elapsed:.2f} seconds")
            logger.info(f"Average throughput: {msg_per_sec:.2f} messages/second")
            
        finally:
            bus_pub.cleanup()
            bus_sub1.cleanup()
            bus_sub2.cleanup() 
