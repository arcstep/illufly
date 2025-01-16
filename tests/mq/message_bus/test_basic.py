import pytest
import asyncio
import zmq
import logging
import os
import time
from urllib.parse import urlparse
from illufly.mq.message_bus import MessageBus

logger = logging.getLogger(__name__)

class TestMessageBusBasic:
    """基础功能测试
    
    设计意图：
    1. 验证消息总线的基本配置和初始化
    2. 验证地址解析和协议支持
    3. 确保资源正确管理和清理
    4. 验证发布者/订阅者的自动角色切换
    """
    
    def setup_method(self):
        """测试前清理环境"""
        # 清理可能存在的 IPC 文件
        if os.path.exists("/tmp/test.ipc"):
            os.remove("/tmp/test.ipc")
            
    def teardown_method(self):
        """测试后清理环境"""
        # 清理测试产生的 IPC 文件
        if os.path.exists("/tmp/test.ipc"):
            os.remove("/tmp/test.ipc")
        
    @pytest.mark.asyncio
    async def test_default_address(self):
        """测试默认地址"""
        bus = MessageBus(logger=logger)
        try:
            assert bus._address == "inproc://message_bus"
        finally:
            bus.cleanup()
            
    @pytest.mark.asyncio
    @pytest.mark.parametrize("address", [
        "tcp://127.0.0.1:0",  # 动态端口
        "tcp://127.0.0.1:1024",  # 低位端口
        "tcp://127.0.0.1:65535",  # 最大端口
        "inproc://test",
        "ipc:///tmp/test.ipc"
    ])
    async def test_valid_addresses(self, address):
        """测试有效地址配置和资源清理"""
        bus = MessageBus(address, logger=logger)
        try:
            assert bus._address == address
            assert bus._pub_socket is not None
            assert bus._sub_socket is not None
        finally:
            bus.cleanup()
            
    @pytest.mark.asyncio
    async def test_async_collect_communication(self):
        """测试异步收集通信"""
        # 创建实例
        bus = MessageBus(logger=logger)
        
        try:
            # 发送测试消息
            bus.subscribe("test")
            bus.publish("test", {"msg": "hello"})
            bus.publish("test")
            time.sleep(0.1)
            resp = bus.async_collect()

            results = []
            async for msg in resp:
                results.append(msg)

            assert len(results) == 2
            assert results[0]["msg"] == "hello"
            
        finally:
            bus.cleanup()

    def test_sync_collect_communication(self):
        """测试同步收集通信"""
        # 创建实例
        bus = MessageBus(logger=logger)
        
        try:
            # 发送测试消息
            bus.subscribe("test")
            bus.publish("test", {"msg": "hello"})
            bus.publish("test")
            time.sleep(0.1)
            received = list(bus.collect())

            assert len(received) == 2
            assert received[0]["msg"] == "hello"
            
        finally:
            bus.cleanup()

    def test_collect_multiple_messages(self):
        """测试收集多条消息"""
        address = "tcp://127.0.0.1:5557"
        bus = MessageBus(address, logger=logger)
        
        try:
            # 先创建订阅，等待连接建立
            time.sleep(0.1)  # 给ZMQ一点时间建立连接
            
            # 发送一系列消息
            bus.publish("test", {"block_type": "start", "content": "hello"})
            bus.publish("test", {"block_type": "data", "content": "world"})
            bus.publish("test", {"block_type": "end", "content": "done"})
            bus.publish("test")
            
            # 收集消息
            messages = list(bus.collect())
            
            # 验证消息
            assert len(messages) == 3
            assert messages[0]["block_type"] == "start"
            assert messages[0]["content"] == "hello"
            assert messages[1]["block_type"] == "data"
            assert messages[1]["content"] == "world"
            assert messages[2]["block_type"] == "end"
            assert messages[2]["content"] == "done"
            
        finally:
            bus.cleanup()
            
    def test_collect_timeout(self):
        """测试消息收集超时"""
        address = "tcp://127.0.0.1:5558"
        bus = MessageBus(address, logger=logger)
        
        try:
            # 发送一条消息但不发送结束标记
            bus.publish("test", {"block_type": "data", "content": "hello"})
            
            # 收集消息，应该在超时后返回
            start_time = time.time()
            messages = list(bus.collect(timeout=0.5))
            elapsed = time.time() - start_time
            
            # 验证结果
            assert len(messages) == 1
            assert messages[0]["content"] == "hello"
            assert 0.4 < elapsed < 0.6  # 验证确实等待了大约0.5秒
            
        finally:
            bus.cleanup()

