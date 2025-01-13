

def run_ipc_publisher(address, ready_event):
    """在另一个进程中运行IPC发布者"""
    # 确保在新进程中也配置logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Publisher process starting with address: {address}")
        bus = MessageBus(address, auto_bind=True, logger=logger)
        bus.start()
        logger.info("Publisher started")
        
        # 等待订阅者准备就绪
        ready_event.wait()
        logger.info("Subscriber ready, sending message")
        
        bus.publish("test", {"msg": "from another process"})
        logger.info("Message published")
        time.sleep(0.1)  # 短暂等待确保消息发送
        bus.cleanup()
        logger.info("Publisher cleaned up")
    except Exception as e:
        logger.error(f"Publisher error: {e}")
        raise

def run_crash_publisher(address, ready_event, crash_event):
    """在另一个进程中运行将要崩溃的发布者"""
    # 确保在新进程中也配置logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Crash publisher starting with address: {address}")
        bus = MessageBus(address, auto_bind=True, logger=logger)
        bus.start()
        logger.info("Crash publisher started")
        
        ready_event.set()
        logger.info("Waiting for crash signal")
        
        # 等待崩溃信号
        crash_event.wait()
        logger.info("Received crash signal, simulating crash")
        
        # 模拟崩溃：不清理直接退出
        os._exit(1)
    except Exception as e:
        logger.error(f"Crash publisher error: {e}")
        raise

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
        ready_event = multiprocessing.Event()
        
        # 启动发布者进程
        process = multiprocessing.Process(
            target=run_ipc_publisher,
            args=(address, ready_event)
        )
        process.start()
        logger.info("Publisher process started")
        
        # 在主进程中订阅
        received = []
        async def subscribe():
            logger.info("Subscriber starting")
            self.bus = MessageBus(address, auto_bind=False, logger=logger)
            self.bus.start()
            logger.info("Subscriber started")
            
            try:
                async with asyncio.timeout(2.0):
                    logger.info("Starting subscription")
                    # 通知发布者可以发送消息了
                    ready_event.set()
                    
                    async for msg in self.bus.subscribe(["test"]):
                        logger.info(f"Received message: {msg}")
                        received.append(msg)
                        break
            except asyncio.TimeoutError:
                logger.error("Subscription timed out")
                raise
            finally:
                logger.info("Subscription completed")
        
        try:
            asyncio.run(subscribe())
        finally:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                logger.warning("Had to terminate publisher process")

    def test_publisher_crash_recovery(self):
        """测试发布者崩溃后的系统恢复"""
        address = "ipc:///tmp/test_recovery.ipc"
        ready_event = multiprocessing.Event()
        crash_event = multiprocessing.Event()
        
        # 启动将要崩溃的发布者
        crash_process = multiprocessing.Process(
            target=run_crash_publisher,
            args=(address, ready_event, crash_event)
        )
        crash_process.start()
        logger.info("Initial publisher process started")
        ready_event.wait()
        
        received = []
        async def subscribe_with_recovery():
            logger.info("Starting subscriber")
            self.bus = MessageBus(address, auto_bind=False, logger=logger)
            self.bus.start()
            
            try:
                async with asyncio.timeout(5.0):
                    subscriber = self.bus.subscribe(["test"])
                    logger.info("Subscription created")
                    await asyncio.sleep(0.5)
                    
                    # 触发发布者崩溃
                    logger.info("Triggering publisher crash")
                    crash_event.set()
                    await asyncio.sleep(0.5)
                    
                    # 清理资源和状态
                    if os.path.exists("/tmp/test_recovery.ipc"):
                        logger.info("Cleaning up stale IPC file")
                        os.remove("/tmp/test_recovery.ipc")
                    
                    # 重置MessageBus的绑定状态
                    logger.info("Resetting MessageBus binding state")
                    MessageBus._bound_socket = None
                    
                    # 启动新的发布者
                    logger.info("Starting new publisher")
                    new_publisher = MessageBus(address, auto_bind=True, logger=logger)
                    new_publisher.start()
                    await asyncio.sleep(0.5)
                    
                    # 确保订阅重新建立
                    logger.info("Re-establishing subscription")
                    await asyncio.sleep(0.5)
                    
                    try:
                        # 发送恢复消息
                        logger.info("Sending recovery message")
                        new_publisher.publish("test", {"msg": "recovered"})
                        
                        logger.info("Waiting for recovery message")
                        async for msg in subscriber:
                            logger.info(f"Received after recovery: {msg}")
                            received.append(msg)
                            break
                    finally:
                        new_publisher.cleanup()
                        
            except asyncio.TimeoutError:
                logger.error("Recovery test timed out")
                raise
            
        try:
            asyncio.run(subscribe_with_recovery())
            
            # 验证恢复后收到消息
            assert len(received) == 1, f"Expected 1 message, got {len(received)}"
            assert received[0]["msg"] == "recovered"
            
        finally:
            logger.info("Test cleanup: checking crash process")
            if crash_process.is_alive():
                logger.warning("Crash process still alive, terminating")
                crash_process.terminate()
            crash_process.join(timeout=1)

    def test_subscriber_reconnection(self):
        """测试订阅者断线重连
        
        验证当网络临时中断后：
        1. 订阅者能够自动重连
        2. 不会丢失重连期间的消息
        3. 系统能够继续正常工作
        """
        address = "tcp://127.0.0.1:5555"  # 使用TCP便于模拟网络中断
        received = []
        
        async def run_reconnection_test():
            # 启动发布者
            publisher = MessageBus(address, auto_bind=True, logger=logger)
            publisher.start()
            
            # 启动订阅者
            self.bus = MessageBus(address, auto_bind=False, logger=logger)
            self.bus.start()
            
            try:
                async with asyncio.timeout(5.0):
                    subscriber = self.bus.subscribe(["test"])
                    
                    # 发送初始消息
                    publisher.publish("test", {"seq": 1})
                    
                    # 接收第一条消息
                    async for msg in subscriber:
                        received.append(msg)
                        if msg["seq"] == 1:
                            break
                    
                    # 模拟网络中断：重启发布者
                    publisher.cleanup()
                    await asyncio.sleep(0.5)
                    publisher = MessageBus(address, auto_bind=True, logger=logger)
                    publisher.start()
                    
                    # 发送恢复后的消息
                    publisher.publish("test", {"seq": 2})
                    
                    # 验证能否收到新消息
                    async for msg in subscriber:
                        received.append(msg)
                        if msg["seq"] == 2:
                            break
                            
            finally:
                publisher.cleanup()
        
        asyncio.run(run_reconnection_test())
        
        # 验证所有消息都收到了
        assert len(received) == 2
        assert [msg["seq"] for msg in received] == [1, 2] 

    def test_auto_recovery(self):
        """测试自动恢复机制
        
        验证：
        1. 发布者崩溃后，新发布者可以自动重用地址
        2. 订阅者可以自动重连
        3. 系统无需手动干预即可恢复
        """
        address = "ipc:///tmp/test_auto_recovery.ipc"
        ready_event = multiprocessing.Event()
        crash_event = multiprocessing.Event()
        
        # 启动将要崩溃的发布者
        crash_process = multiprocessing.Process(
            target=run_crash_publisher,
            args=(address, ready_event, crash_event)
        )
        crash_process.start()
        ready_event.wait()
        
        received = []
        async def subscribe_with_auto_recovery():
            self.bus = MessageBus(
                address, 
                auto_bind=False,
                logger=logger
            )
            self.bus.start()
            
            try:
                async with asyncio.timeout(5.0):
                    subscriber = self.bus.subscribe(["test"])
                    
                    # 触发发布者崩溃
                    crash_event.set()
                    await asyncio.sleep(0.5)
                    
                    # 启动新的发布者 - 应该能自动处理残留资源
                    new_publisher = MessageBus(
                        address, 
                        auto_bind=True,
                        logger=logger
                    )
                    new_publisher.start()
                    
                    # 发送恢复后的消息
                    new_publisher.publish("test", {"msg": "recovered"})
                    
                    try:
                        async for msg in subscriber:
                            logger.info(f"Received after recovery: {msg}")
                            received.append(msg)
                            break
                    finally:
                        new_publisher.cleanup()
                        
            except asyncio.TimeoutError:
                logger.error("Recovery test timed out")
                raise
            
        try:
            asyncio.run(subscribe_with_auto_recovery())
            assert len(received) == 1
            assert received[0]["msg"] == "recovered"
            
        finally:
            if crash_process.is_alive():
                crash_process.terminate()
            crash_process.join(timeout=1)
