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

    def test_inproc_auto_binding_and_connecting(self):
        """测试进程内自动绑定和连接"""
        assert MessageBus._bound_socket is None

        self.bus1 = MessageBus("inproc://test", logger=logger)
        self.bus2 = MessageBus("inproc://test", logger=logger)

        # 第二个实例应该不会重复绑定
        assert self.bus1._pub_socket == MessageBus._bound_socket
        assert self.bus2._sub_socket

    def test_ipc_auto_binding_and_connecting(self, tmp_path):
        """测试IPC自动绑定和连接"""
        assert MessageBus._bound_socket is None
        
        # 使用较短的IPC路径
        ipc_path = os.path.join(tmp_path, "test.ipc")
        if os.path.exists(ipc_path):
            os.remove(ipc_path)
        address = f"ipc://{ipc_path}"
        
        self.bus1 = MessageBus(address, logger=logger)
        assert self.bus1._is_ipc
        assert self.bus1._bound_socket
        assert MessageBus._bound_socket
        
        # 验证IPC文件创建
        # assert os.path.exists(ipc_path)
        
        # 清理
        self.bus1.cleanup()
        assert not os.path.exists(ipc_path)

    def test_tcp_binding_and_connecting(self):
        """测试TCP绑定"""
        assert MessageBus._bound_socket is None

        address = "tcp://127.0.0.1:5555"
        self.bus1 = MessageBus(address, logger=logger)
        self.bus2 = MessageBus(address, logger=logger)
        
        assert self.bus1._pub_socket == MessageBus._bound_socket
        assert self.bus2._sub_socket
