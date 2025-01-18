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
    async def test_stream_collect(self):
        """测试流式收集"""
        topic = "test_stream"
        bus = MessageBus()
        
        # 发送开始消息
        start_block = StreamingBlock(
            block_type=BlockType.START,
            content="开始处理",
            topic=topic
        )
        bus.publish(topic, start_block)
        
        # 等待第一条消息
        first_message_received = asyncio.Event()
        total_steps = 4
        
        async def publish_messages():
            """发布消息"""
            await first_message_received.wait()
            
            # 发送进度消息
            for i in range(total_steps):
                progress = StreamingBlock(
                    block_type=BlockType.PROGRESS,
                    block_content={
                        "step": i + 1,
                        "total_steps": total_steps,
                        "percentage": ((i + 1) / total_steps) * 100,
                        "message": f"处理第 {i + 1}/{total_steps} 步"
                    },
                    topic=topic
                )
                bus.publish(topic, progress)
                await asyncio.sleep(0.1)
            
            # 发送结束消息
            end_block = StreamingBlock(
                block_type=BlockType.END,
                content="处理完成",
                topic=topic
            )
            bus.publish(topic, end_block)
        
        # 启动发布任务
        publish_task = asyncio.create_task(publish_messages())
        
        # 收集消息
        blocks = []
        async for block in bus.async_collect():
            blocks.append(block)
            if len(blocks) == 1:
                first_message_received.set()
        
        # 等待发布任务完成
        await publish_task
        
        # 验证消息
        assert len(blocks) == total_steps + 2  # 开始 + 进度消息 + 结束
        assert blocks[0].block_type == BlockType.START
        
        # 验证进度消息
        for i in range(total_steps):
            progress = blocks[i + 1].get_progress()
            assert progress is not None
            assert progress.step == i + 1
            assert progress.total_steps == total_steps
            assert progress.percentage == ((i + 1) / total_steps) * 100
            assert progress.message == f"处理第 {i + 1}/{total_steps} 步"
        
        assert blocks[-1].block_type == BlockType.END 