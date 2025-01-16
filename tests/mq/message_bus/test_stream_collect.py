import pytest
import asyncio
import time
import logging
from illufly.mq.message_bus import MessageBus

logger = logging.getLogger(__name__)

class TestMessageBusStream:
    """消息总线流处理能力测试
    
    设计意图：
    1. 验证消息是否能够实时流式传递
    2. 测量消息从发布到接收的延迟
    3. 确保不会出现消息积压
    4. 验证同步和异步收集的流处理能力
    """
    
    @pytest.mark.asyncio
    async def test_async_stream_collect(self):
        """测试异步流收集的实时性"""
        bus = MessageBus(logger=logger)
        try:
            bus.subscribe("test")
            publish_times = []
            receive_times = []
            messages = []
            
            # 启动异步收集任务
            async def collect_messages():
                async for msg in bus.async_collect():
                    receive_times.append(time.time())
                    messages.append(msg)
                    if msg.get("block_type") == "end":
                        break
                        
            # 启动收集任务
            collect_task = asyncio.create_task(collect_messages())
            
            # 等待订阅生效
            await asyncio.sleep(0.01)
            
            # 按间隔发送消息
            for i in range(5):
                publish_times.append(time.time())
                bus.publish("test", {
                    "index": i,
                    "publish_time": publish_times[-1]
                })
                await asyncio.sleep(0.1)
            
            # 发送结束标记
            publish_times.append(time.time())
            bus.publish("test", {
                "index": 5,
                "block_type": "end",
                "publish_time": publish_times[-1]
            })
            
            # 等待收集完成
            await collect_task
            
            # 验证消息数量
            assert len(messages) == 6, "应该收到6条消息"
            
            # 验证消息顺序
            for i, msg in enumerate(messages):
                assert msg["index"] == i, f"消息顺序错误: {msg}"
            
            # 验证消息延迟
            for msg, receive_time in zip(messages, receive_times):
                delay = receive_time - msg["publish_time"]
                assert delay >= 0, "接收时间不能早于发布时间"
                assert delay < 0.05, f"消息延迟过大: {delay:.3f}秒"
                
            # 验证发布间隔
            for i in range(1, len(publish_times)):
                interval = publish_times[i] - publish_times[i-1]
                assert 0.08 <= interval <= 0.12, f"发布间隔异常: {interval:.3f}秒"
                
        finally:
            bus.cleanup()
            
    def test_sync_stream_collect(self):
        """测试同步流收集的实时性"""
        bus = MessageBus(logger=logger)
        try:
            bus.subscribe("test")
            publish_times = []
            receive_times = []
            messages = []
            
            # 启动一个后台任务发送消息
            async def publish_messages():
                await asyncio.sleep(0.01)  # 等待订阅生效
                for i in range(5):
                    publish_times.append(time.time())
                    bus.publish("test", {
                        "index": i,
                        "publish_time": publish_times[-1]
                    })
                    await asyncio.sleep(0.1)
                
                publish_times.append(time.time())
                bus.publish("test", {
                    "index": 5,
                    "block_type": "end",
                    "publish_time": publish_times[-1]
                })
            
            # 在后台运行发布任务
            loop = asyncio.get_event_loop()
            publish_task = loop.create_task(publish_messages())
            
            # 同步收集消息
            for msg in bus.collect():
                receive_times.append(time.time())
                messages.append(msg)
                if msg.get("block_type") == "end":
                    break
            
            # 等待发布任务完成
            loop.run_until_complete(publish_task)
            
            # 验证消息数量和顺序
            assert len(messages) == 6, "应该收到6条消息"
            for i, msg in enumerate(messages):
                assert msg["index"] == i, f"消息顺序错误: {msg}"
            
            # 验证消息延迟
            for msg, receive_time in zip(messages, receive_times):
                delay = receive_time - msg["publish_time"]
                assert delay >= 0, "接收时间不能早于发布时间"
                assert delay < 0.05, f"消息延迟过大: {delay:.3f}秒"
                
            # 验证发布间隔
            for i in range(1, len(publish_times)):
                interval = publish_times[i] - publish_times[i-1]
                assert 0.08 <= interval <= 0.12, f"发布间隔异常: {interval:.3f}秒"
                
        finally:
            bus.cleanup() 