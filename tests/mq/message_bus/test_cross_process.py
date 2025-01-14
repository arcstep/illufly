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

class TestCrossProcessCommunication:
    """跨进程通信测试
    
    设计意图：
    1. 验证 IPC/TCP 跨进程消息传递
    2. 确保消息的可靠投递
    3. 验证进程间资源的正确管理
    4. 测试异常情况下的系统恢复能力
    """
    
    def setup_method(self, method):
        MessageBus._bound_socket = None
    
    def teardown_method(self, method):
        if hasattr(self, 'bus'):
            self.bus.cleanup()

    def test_ipc_cross_process(self, caplog):
        """测试IPC跨进程通信"""
        address = "ipc:///tmp/test_cross_process.ipc"
        # 确保开始测试时文件不存在
        path = urlparse(address).path
        if os.path.exists(path):
            os.unlink(path)
        subscribe_done = multiprocessing.Event()
        collect_event = multiprocessing.Event()
        
        # 启动发布者进程
        process = multiprocessing.Process(
            target=run_ipc_publisher,
            args=(address, subscribe_done, collect_event)
        )
        process.start()
        logger.info(f"启动订阅者子进程，PID: {process.pid}")
        logger.info(f"订阅者子进程状态: {process.is_alive()}")

        # 在主进程中订阅
        received = []
        try:
            self.bus = MessageBus(address, to_bind=False, to_connect=True, logger=logger)
            self.bus.subscribe(["test"])
            logger.info("我订阅了，等待子进程发布消息 ... ")
            time.sleep(0.2)  # 给订阅一些建立的时间
            subscribe_done.set()
            received = list(self.bus.collect())
            logger.info(f"我收到消息了，消息数量: {len(received)}，你可以退出")
        except Exception as e:
            logger.error(f"订阅超时，发布者状态: {process.is_alive()}")
            if process.exitcode is not None:
                logger.error(f"Publisher process exited with code: {process.exitcode}")
            raise
        finally:
            collect_event.set()
            process.join(timeout=1)
            if process.is_alive():
                logger.warning("已经过了1秒，你还没退出，不得不强行终止")
                process.terminate()
            logger.info(f"发布者进程最终退出码: {process.exitcode}")

def run_ipc_publisher(address, subscribe_done, collect_event):
    """在另一个进程中运行IPC发布者"""    
    logging.basicConfig(level=logging.DEBUG)

    try:
        logger.info(f"发布者绑定到地址: {address}")
        bus = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
        logger.info("我是发布者，等你准备好订阅我就继续 ... ")
        
        subscribe_done.wait()
        time.sleep(0.2)  # 给订阅一些建立的时间
        bus.publish("test", {"msg": "from another process"})
        bus.publish("test", end=True)
        
        # 等待主进程通知可以退出
        logger.info("我已经发布完消息，等你接收完就通知我退出")
        collect_event.wait()
        logger.info("我现在退出了")
        
        bus.cleanup()
        logger.info("Publisher cleaned up")
    except Exception as e:
        logger.error(f"Publisher error: {e}", exc_info=True)
        raise
