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

@pytest.fixture(autouse=True)
def setup_log(caplog):
    caplog.set_level(logging.DEBUG)

class TestMessageBusBinding:
    """绑定行为测试
    
    设计意图：
    1. 验证进程内通信的自动绑定机制
    2. 验证地址冲突时的自动切换行为
    3. 确保多实例间的协调工作
    4. 验证不同协议下的绑定行为差异
    """
    
    def setup_method(self, method):
        MessageBus._bound_socket = None
        
    def teardown_method(self, method):
        if hasattr(self, 'bus1'):
            self.bus1.cleanup()
        if hasattr(self, 'bus2'):
            self.bus2.cleanup()

    def test_inproc_auto_binding(self):
        """测试进程内自动绑定"""
        self.bus1 = MessageBus("inproc://test", logger=logger)
        self.bus1.start()
        assert MessageBus._bound_socket == "inproc://test"
        
        self.bus2 = MessageBus("inproc://test", logger=logger)
        self.bus2.start()
        # 第二个实例应该不会重复绑定
        assert MessageBus._bound_socket == "inproc://test"

    def test_ipc_auto_binding(self):
        """测试IPC自动绑定"""
        address = "ipc:///tmp/test_bus.ipc"
        self.bus1 = MessageBus(address, auto_bind=True, logger=logger)
        self.bus1.start()
        
        # 验证IPC文件创建
        path = urlparse(address).path
        assert os.path.exists(path)
        
        # 清理
        self.bus1.cleanup()
        assert not os.path.exists(path)

    def test_tcp_binding(self, caplog):
        """测试TCP绑定和自动切换到连接模式"""
        address = "tcp://127.0.0.1:5555"
        
        self.bus1 = MessageBus(address, auto_bind=True, logger=logger)
        self.bus1.start()
        
        # 第二个实例应该自动切换为连接模式
        self.bus2 = MessageBus(address, auto_bind=True, logger=logger)
        self.bus2.start()
        
        # 验证警告日志
        assert any("Address in use, connected to:" in record.message 
                  for record in caplog.records)
        
        # 清除日志记录
        caplog.clear()