from unittest.mock import patch, MagicMock
import zmq
import pytest
import asyncio
import os
import multiprocessing
import time
import logging
logger = logging.getLogger(__name__)

from urllib.parse import urlparse
from illufly.mq.message_bus import MessageBus, BindState
from illufly.mq.utils import is_ipc

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
        MessageBus._bound_state = BindState.UNBOUND
        MessageBus._bound_refs = 0
        
    def teardown_method(self, method):
        if hasattr(self, 'bus1'):
            self.bus1.cleanup()
        if hasattr(self, 'bus2'):
            self.bus2.cleanup()

    def test_remote_binding(self):
        """测试远程服务器绑定"""
        # 创建一个模拟的 socket 对象
        mock_socket = MagicMock()
        mock_socket.bind = MagicMock()  # 模拟 bind 方法
        
        # 模拟远程绑定
        with patch.object(zmq.Context, 'socket', return_value=mock_socket):
            address = "tcp://example.com:5555"  # 使用非本地地址
            bus = MessageBus(address, logger=logger)
            
            assert MessageBus._bound_state == BindState.REMOTE_BOUND, "应该识别为远程绑定"
            assert bus.is_bound_outside is True
            assert MessageBus._bound_refs == 0, "远程绑定不应使用引用计数"

    def test_tcp_cross_process_binding(self):
        """测试TCP跨进程绑定行为"""
        address = "tcp://127.0.0.1:5556"
        ready_event = multiprocessing.Event()
        
        # 启动外部进程
        process = multiprocessing.Process(
            target=run_external_binder,
            args=(address, ready_event)
        )
        process.start()
        
        try:
            # 等待外部进程绑定完成
            ready_event.wait()
            
            # 在 init_bound_socket 层面模拟绑定失败
            with patch('illufly.mq.utils.init_bound_socket') as mock_init:
                # 模拟地址已被占用的情况
                mock_init.return_value = (True, None)  # (already_bound, socket_result)
                
                # 主进程尝试绑定同一地址
                self.bus1 = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
                
                # 应该发现地址被外部进程占用
                assert self.bus1._pub_socket is None
                assert MessageBus._bound_state == BindState.EXTERNAL_BOUND, "应该识别为外部绑定"
                assert self.bus1.is_bound_outside is True
                
                # 尝试作为订阅者连接
                self.bus2 = MessageBus(address, to_bind=False, to_connect=True, logger=logger)
                assert self.bus2._sub_socket is not None
                assert self.bus2.is_connected is True
                
        finally:
            process.terminate()
            process.join(timeout=1)

def run_external_binder(address, ready_event):
    """外部绑定进程"""
    print("--------------------------------")
    print(f"External binder process starting: PID={os.getpid()}")
    print("--------------------------------", flush=True)
    
    try:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)-8s PID=%(process)d %(name)s:%(filename)s:%(lineno)d %(message)s',
            force=True
        )
        logger = logging.getLogger(__name__)
        
        logger.info(f"External process trying to bind: {address}")
        bus = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
        logger.info(f"External process socket created: {bus._pub_socket}")
        
        # 确保绑定成功
        if bus._pub_socket is None:
            logger.error("Failed to create socket")
            raise RuntimeError("Socket creation failed")
            
        # 发送一些测试消息确保socket工作
        bus.publish("test", {"msg": "test"})
        logger.info("Test message published")
        
        # 设置就绪事件
        ready_event.set()
        logger.info("Ready event set")
        
        # 保持运行直到主进程完成测试
        time.sleep(2.0)
        logger.info("External process exiting")
        
    except Exception as e:
        print(f"External binder error: {e}", flush=True)
        logger.error(f"External binder error: {e}", exc_info=True)
        ready_event.set()  # 即使失败也要设置事件
        raise