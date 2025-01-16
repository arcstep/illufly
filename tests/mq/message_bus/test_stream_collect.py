import pytest
import asyncio
import time
import logging
from illufly.mq.message_bus import MessageBus

logger = logging.getLogger(__name__)

class TestMessageBusStream:
    """消息总线流处理能力测试
    
    设计意图：
    1. 验证消息的实时流式处理能力
    2. 验证发布和接收的并行处理能力
    3. 测量端到端延迟
    4. 验证资源正确管理和清理
    
    使用要点：
    1. 初始化和消息收发：
        # 创建并初始化消息总线
        bus = MessageBus(logger=logger)
        bus.subscribe("test")
        
        # 发送初始消息
        initial_time = time.time()
        bus.publish("test", {
            "index": 0,
            "publish_time": initial_time
        })
    
    2. 异步流处理模式：
        # 创建收集器并保存引用
        collector = bus.async_collect()
        async for msg in collector:
            receive_time = time.time()
            # 处理消息...
            if msg.get("block_type") == "end":
                break
    
    3. 并行处理协调：
        # 使用事件同步发布和接收
        received_first = asyncio.Event()
        publisher_done = asyncio.Event()
        
        async def publisher():
            await received_first.wait()  # 等待接收者就绪
            for i in range(4):
                bus.publish("test", {...})
                await asyncio.sleep(0.1)
        
        # 在接收端通知发布者
        async for msg in collector:
            if len(messages) == 1:
                received_first.set()
    
    4. 资源清理顺序：
        try:
            # 业务逻辑
        finally:
            # 1. 取消发布任务
            if not publisher_task.done():
                publisher_task.cancel()
                await publisher_task
            
            # 2. 关闭收集器
            if collector is not None:
                await collector.aclose()
            
            # 3. 清理消息总线
            await asyncio.sleep(0.01)
            bus.cleanup()
    
    性能指标：
    1. 消息延迟 < 10ms：
        delay = receive_time - msg["publish_time"]
        assert delay < 0.01
    
    2. 发布间隔稳定（100ms）：
        interval = publish_times[i] - publish_times[i-1]
        assert 0.08 <= interval <= 0.12
    
    调试建议：
    1. 使用事件记录关键点：
        logger.debug("First message received, signaling publisher")
        logger.debug("Publisher starting after first message received")
    
    2. 监控消息处理：
        - 记录发布时间：publish_times.append(time.time())
        - 记录接收时间：receive_times.append(time.time())
        - 验证消息顺序：assert msg["index"] == i
    
    注意事项：
    1. 必须显式关闭异步生成器（await collector.aclose()）
    2. 使用事件协调异步任务的执行顺序
    3. 按正确顺序清理资源（发布任务 -> 收集器 -> 消息总线）
    4. 验证消息的实时性和顺序性
    """
    
    @pytest.mark.asyncio
    async def test_async_stream_collect(self):
        """测试异步流收集的实时性和并行处理能力
        
        验证：
        1. 消息能够实时流式处理
        2. 发布和接收可以并行执行
        3. 消息延迟在可接受范围内（<10ms）
        4. 资源能够正确释放
        5. 消息顺序和完整性得到保证
        """
        bus = MessageBus(logger=logger)
        bus.subscribe("test")
        
        publish_times = []
        receive_times = []
        messages = []
        
        received_first = asyncio.Event()
        publisher_done = asyncio.Event()
        
        async def publisher():
            await received_first.wait()
            logger.debug("Publisher starting after first message received")
            
            for i in range(4):
                publish_time = time.time()
                publish_times.append(publish_time)
                bus.publish("test", {
                    "index": i + 1,
                    "publish_time": publish_time
                })
                await asyncio.sleep(0.1)
            
            final_time = time.time()
            publish_times.append(final_time)
            bus.publish("test", {
                "index": 5,
                "block_type": "end",
                "publish_time": final_time
            })
            publisher_done.set()
        
        publisher_task = asyncio.create_task(publisher())
        collector = None  # 保存收集器引用
        
        try:
            initial_time = time.time()
            publish_times.append(initial_time)
            bus.publish("test", {
                "index": 0,
                "publish_time": initial_time
            })
            
            # 创建收集器并保存引用
            collector = bus.async_collect()
            async for msg in collector:
                receive_time = time.time()
                receive_times.append(receive_time)
                messages.append(msg)
                
                if len(messages) == 1:
                    received_first.set()
                    logger.debug("First message received, signaling publisher")
                
                delay = receive_time - msg["publish_time"]
                assert delay < 0.01, f"消息 {msg['index']} 延迟过大: {delay:.3f}秒"
                
                if msg.get("block_type") == "end":
                    break
            
            await publisher_done.wait()
            await publisher_task
            
            # 验证消息处理
            assert len(messages) == 6, "应该收到6条消息（5条数据 + 1条结束标记）"
            assert len(receive_times) == 6, "应该有6个接收时间点"
            assert len(publish_times) == 6, "应该有6个发布时间点"
            
            # 验证消息顺序
            for i, msg in enumerate(messages[:-1]):  # 除去结束标记
                assert msg["index"] == i, f"消息顺序错误: {msg}"
            
            # 验证发布间隔（确认发布者确实是慢速的）
            for i in range(1, len(publish_times)):
                interval = publish_times[i] - publish_times[i-1]
                if i > 1:  # 跳过第一个间隔，因为它包含了等待时间
                    assert 0.08 <= interval <= 0.12, f"发布间隔异常: {interval:.3f}秒"
            
            # 验证消息的实时性
            for i in range(len(messages)):
                processing_delay = receive_times[i] - publish_times[i]
                assert processing_delay < 0.01, f"消息 {i} 处理延迟过大: {processing_delay:.3f}秒"
                
        finally:
            # 按顺序清理资源
            if not publisher_task.done():
                publisher_task.cancel()
                try:
                    await publisher_task
                except asyncio.CancelledError:
                    pass
            
            # 正确关闭收集器
            if collector is not None:
                try:
                    await collector.aclose()  # 显式关闭异步生成器
                except Exception as e:
                    logger.debug(f"Error closing collector: {e}")
            
            # 最后清理消息总线
            await asyncio.sleep(0.01)  # 给予一点时间完成清理
            bus.cleanup()
            
    def test_sync_stream_collect(self):
        """测试同步流收集的实时性和并行处理能力"""
        bus = MessageBus(logger=logger)
        try:
            bus.subscribe("test")
            publish_times = []
            processing_times = []
            receive_times = []
            messages = []
            
            # 后台慢速发布任务
            async def slow_publisher():
                await asyncio.sleep(0.01)  # 等待订阅生效
                for i in range(5):
                    start = time.time()
                    bus.publish("test", {
                        "index": i,
                        "publish_time": start
                    })
                    processing_time = time.time() - start
                    processing_times.append(processing_time)
                    publish_times.append(start)
                    await asyncio.sleep(0.1)  # 模拟耗时操作
                
                end_time = time.time()
                bus.publish("test", {
                    "index": 5,
                    "block_type": "end",
                    "publish_time": end_time
                })
                publish_times.append(end_time)
            
            # 在后台运行发布任务
            loop = asyncio.get_event_loop()
            publish_task = loop.create_task(slow_publisher())
            
            # 同步收集消息
            for msg in bus.collect():
                receive_time = time.time()
                receive_times.append(receive_time)
                messages.append(msg)
                
                # 计算消息延迟
                delay = receive_time - msg["publish_time"]
                assert delay < 0.01, f"消息 {msg['index']} 的延迟过大: {delay:.3f}秒"
                
                if msg.get("block_type") == "end":
                    break
            
            # 等待发布任务完成
            loop.run_until_complete(publish_task)
            
            # 执行与异步测试相同的验证
            assert len(messages) == 6, "应该收到6条消息"
            assert len(receive_times) == 6, "应该有6个接收时间点"
            assert len(publish_times) == 6, "应该有6个发布时间点"
            
            # 验证消息顺序
            for i, msg in enumerate(messages[:-1]):
                assert msg["index"] == i, f"消息顺序错误: {msg}"
            
            # 验证发布间隔
            for i in range(1, len(publish_times)):
                interval = publish_times[i] - publish_times[i-1]
                assert 0.08 <= interval <= 0.12, f"发布间隔异常: {interval:.3f}秒"
            
            # 验证处理性能
            for pt in processing_times:
                assert pt < 0.01, f"消息发布处理时间过长: {pt:.3f}秒"
            
            # 验证第一条消息的响应时间
            first_delay = receive_times[0] - publish_times[0]
            assert first_delay < 0.01, f"获取第一条消息延迟过大: {first_delay:.3f}秒"
                
        finally:
            bus.cleanup() 