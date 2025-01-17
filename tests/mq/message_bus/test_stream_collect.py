import pytest
import asyncio
import time
import logging
from illufly.mq.message_bus import MessageBus
from illufly.mq.models import StreamingBlock, BlockType, ProgressContent

logger = logging.getLogger(__name__)

class TestMessageBusStream:
    """消息总线流处理能力测试"""
    
    @pytest.mark.asyncio
    async def test_async_stream_collect(self):
        """测试异步流收集的实时性和并行处理能力"""
        bus = MessageBus(logger=logger)
        topic = "test_stream"
        bus.subscribe(topic)
        
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
                
                # 创建带进度的消息块
                progress = StreamingBlock.create_progress(
                    percentage=(i + 1) * 25.0,
                    message=f"处理第 {i + 1} 步",
                    step=i + 1,
                    total_steps=4,
                    topic=topic,
                    seq=i + 1
                )
                bus.publish(topic, progress.model_dump())
                await asyncio.sleep(0.1)
            
            final_time = time.time()
            publish_times.append(final_time)
            end_block = StreamingBlock(
                block_type=BlockType.END,
                content="处理完成",
                topic=topic,
                seq=5
            )
            bus.publish(topic, end_block.model_dump())
            publisher_done.set()
        
        publisher_task = asyncio.create_task(publisher())
        collector = None
        
        try:
            initial_time = time.time()
            publish_times.append(initial_time)
            start_block = StreamingBlock(
                block_type=BlockType.START,
                content="开始处理",
                topic=topic,
                seq=0
            )
            bus.publish(topic, start_block.model_dump())
            
            collector = bus.async_collect()
            async for msg in collector:
                receive_time = time.time()
                receive_times.append(receive_time)
                block = StreamingBlock.model_validate(msg)
                messages.append(block)
                
                if len(messages) == 1:
                    received_first.set()
                    logger.debug("First message received, signaling publisher")
                
                # 验证进度消息的结构
                if block.block_type == BlockType.PROGRESS:
                    progress_content = block.get_structured_content()
                    assert isinstance(progress_content, ProgressContent)
                    assert 0 <= progress_content.percentage <= 100
                    assert progress_content.step <= progress_content.total_steps
                
                if block.block_type == BlockType.END:
                    break
            
            await publisher_done.wait()
            await publisher_task
            
            # 验证消息处理
            assert len(messages) == 6, "应该收到6条消息（开始+4条进度+结束）"
            assert len(receive_times) == 6, "应该有6个接收时间点"
            assert len(publish_times) == 6, "应该有6个发布时间点"
            
            # 验证消息顺序和类型
            assert messages[0].block_type == BlockType.START, "第一条应该是开始消息"
            for i, msg in enumerate(messages[1:-1]):
                assert msg.block_type == BlockType.PROGRESS, f"消息 {i+1} 应该是进度块"
                progress = msg.get_structured_content()
                assert progress.percentage == (i + 1) * 25.0, f"进度值错误: {progress.percentage}"
            assert messages[-1].block_type == BlockType.END, "最后一条应该是结束消息"
            
        finally:
            if not publisher_task.done():
                publisher_task.cancel()
                try:
                    await publisher_task
                except asyncio.CancelledError:
                    pass
            
            if collector is not None:
                try:
                    await collector.aclose()
                except Exception as e:
                    logger.debug(f"Error closing collector: {e}")
            
            await asyncio.sleep(0.01)
            bus.cleanup() 