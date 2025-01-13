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

    def test_ipc_cross_process(self):
        """测试IPC跨进程通信"""
        address = "ipc:///tmp/test_cross_process.ipc"
        subscribe_event = multiprocessing.Event()
        done_event = multiprocessing.Event()
        
        # 启动发布者进程
        process = multiprocessing.Process(
            target=run_ipc_publisher,
            args=(address, subscribe_event, done_event)
        )
        process.start()
        logger.info(f"Publisher process started with PID: {process.pid}")
        logger.info(f"Publisher process is alive: {process.is_alive()}")

        # 在主进程中订阅
        received = []
        async def subscribe():
            try:
                async with asyncio.timeout(3.0):
                    logger.info("Starting subscription")
                    self.bus = MessageBus(address, to_bind=False, to_connect=True, logger=logger)
                    logger.info("Subscriber started")
                    sub_results = self.bus.subscribe(["test"])
                    await asyncio.sleep(0.1)
                    subscribe_event.set()
                    async for msg in sub_results:
                        logger.info(f"Received message: {msg}")
                        received.append(msg)
                        break
            except asyncio.TimeoutError:
                logger.error(f"Subscription timed out, publisher alive: {process.is_alive()}")
                if process.exitcode is not None:
                    logger.error(f"Publisher process exited with code: {process.exitcode}")
                raise
            finally:
                logger.info("Subscription completed")
        
        try:
            asyncio.run(subscribe())
        finally:
            # 通知发布者可以退出了
            logger.info("Signaling publisher to exit")
            done_event.set()
            process.join(timeout=1)
            if process.is_alive():
                logger.warning("Had to terminate publisher process")
                process.terminate()
            logger.info(f"Publisher process final exit code: {process.exitcode}")

def run_ipc_publisher(address, subscribe_event, done_event):
    """在另一个进程中运行IPC发布者"""    
    try:
        logger.info(f"Publisher process starting with address: {address}")
        bus = MessageBus(address, to_bind=True, to_connect=False, logger=logger)
        logger.info("Publisher started")
        
        subscribe_event.wait()
        time.sleep(0.2)  # 给订阅一些建立的时间
        bus.publish("test", {"msg": "from another process"})
        logger.info("Message published")
        
        # 等待主进程通知可以退出
        logger.info("Waiting for done signal")
        done_event.wait()
        logger.info("Received done signal, cleaning up")
        
        bus.cleanup()
        logger.info("Publisher cleaned up")
    except Exception as e:
        logger.error(f"Publisher error: {e}", exc_info=True)
        raise
