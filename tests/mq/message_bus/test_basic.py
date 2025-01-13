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
    
    def setup_method(self, method):
        MessageBus._bound_socket = None
        
    @pytest.mark.asyncio
    async def test_default_address(self):
        """测试默认地址"""
        bus = MessageBus()
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
        bus = MessageBus(address, role="publisher")
        try:
            assert bus._address == address
            assert bus._pub_socket is not None
        finally:
            bus.cleanup()
            
    @pytest.mark.asyncio
    async def test_pub_sub_communication(self):
        """测试显式发布订阅通信"""
        address = "tcp://127.0.0.1:5556"
        
        # 创建实例
        bus_pub = MessageBus(address, role="publisher")
        bus_sub = MessageBus(address, role="subscriber")
        
        try:
            # 等待订阅者准备就绪
            # await bus_sub.ensure_ready()
            
            # 创建接收任务
            received = []
            receive_task = asyncio.create_task(
                self._receive_message(bus_sub, received)
            )
            
            # 给接收任务一点时间启动
            await asyncio.sleep(0.1)
            
            # 发送测试消息
            bus_pub.publish("test", {"msg": "hello"})
            
            # 等待接收完成
            try:
                await asyncio.wait_for(receive_task, timeout=1.0)
            except asyncio.TimeoutError:
                receive_task.cancel()
                raise
                
            assert len(received) == 1
            assert received[0]["msg"] == "hello"
            
        finally:
            bus_pub.cleanup()
            bus_sub.cleanup()
            
    async def _receive_message(self, bus, received):
        """接收消息的辅助方法"""
        bus._sub_socket.subscribe(b"test")
        async for msg in bus.subscribe(["test"]):
            if msg.get("topic") != "_heartbeat":
                received.append(msg)
                break

