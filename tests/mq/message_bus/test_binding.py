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

    def test_ipc_cross_process_binding(self, tmp_path, capfd):
        """测试IPC跨进程绑定行为"""
        ipc_path = os.path.join(tmp_path, "test_cross.ipc")
        address = f"ipc://{ipc_path}"
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
            
            # 捕获并打印输出
            out, err = capfd.readouterr()
            logger.info(f"Child process stdout: {out}")
            logger.info(f"Child process stderr: {err}")
            
            # 主进程尝试绑定同一地址
            self.bus1 = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
            
            # 应该发现地址被外部进程占用
            assert self.bus1._pub_socket is None
            assert MessageBus._bound_socket is True
            assert self.bus1.is_bound_outside is True
            
            # 尝试作为订阅者连接
            self.bus2 = MessageBus(address, to_bind=False, to_connect=True, logger=logger)
            assert self.bus2._sub_socket is not None
            assert self.bus2.is_connected is True
            
        finally:
            process.terminate()
            process.join(timeout=1)
            if os.path.exists(ipc_path):
                os.remove(ipc_path)
                
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
            
            # 主进程尝试绑定同一地址
            self.bus1 = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
            
            # 应该发现地址被外部进程占用
            assert self.bus1._pub_socket is None
            assert MessageBus._bound_socket is True
            assert self.bus1.is_bound_outside is True
            
            # 尝试作为订阅者连接
            self.bus2 = MessageBus(address, to_bind=False, to_connect=True, logger=logger)
            assert self.bus2._sub_socket is not None
            assert self.bus2.is_connected is True
            
        finally:
            process.terminate()
            process.join(timeout=1)

def run_external_binder(address, ready_event):
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