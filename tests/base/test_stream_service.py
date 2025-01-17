import pytest
import asyncio
import time
from illufly.base.base_service import BaseService
from illufly.mq.message_bus import MessageBus
from illufly.mq.models import StreamingBlock, BlockType

class StreamService(BaseService):
    """用于测试的流处理服务"""
    def __init__(self, service_name: str = "stream_service", message_bus_address: str = None):
        super().__init__(service_name, message_bus_address)
        self.register_method("server", async_handle=self._stream_handler)
    
    async def _stream_handler(self, message: str, thread_id: str, message_bus: MessageBus):
        """模拟流式处理
        
        发送5条消息：
        1. 开始处理
        2-4. 处理块1-3
        5. 结束处理
        """
        # 发送开始消息
        message_bus.publish(thread_id, StreamingBlock(
            block_type=BlockType.START,
            content=f"开始处理: {message}",
            topic=thread_id
        ).model_dump())
        
        # 发送3个处理块
        for i in range(3):
            await asyncio.sleep(0.1)
            message_bus.publish(thread_id, StreamingBlock(
                block_type=BlockType.CHUNK,
                content=f"处理块 {i+1}: {message}",
                topic=thread_id
            ).model_dump())
            
        # 发送结束消息
        message_bus.publish(thread_id, StreamingBlock(
            block_type=BlockType.END,
            content=f"处理完成: {message}",
            topic=thread_id
        ).model_dump())

@pytest.mark.parametrize("is_async", [True, False])
@pytest.mark.asyncio
async def test_stream_processing(is_async):
    """测试流处理的实时性"""
    service = StreamService()
    blocks = []
    receive_times = []
    
    try:
        if is_async:
            response = await service.async_call(message="流处理测试")
            async for block in response:
                assert isinstance(block, StreamingBlock)
                blocks.append(block)
                receive_times.append(time.time())
                if block.block_type == BlockType.END:
                    break
        else:
            response = service.call(message="流处理测试")
            for block in response:
                assert isinstance(block, StreamingBlock)
                blocks.append(block)
                receive_times.append(time.time())
                if block.block_type == BlockType.END:
                    break
                    
        # 验证消息内容
        assert len(blocks) == 5  # 开始 + 3个块 + 结束
        assert all(isinstance(block, StreamingBlock) for block in blocks)
        
        # 验证消息顺序和类型
        assert blocks[0].block_type == BlockType.START
        assert blocks[0].content.startswith("开始处理")
        
        for i in range(1, 4):
            assert blocks[i].block_type == BlockType.CHUNK
            assert blocks[i].content.startswith(f"处理块 {i}")
            
        assert blocks[-1].block_type == BlockType.END
        assert blocks[-1].content.startswith("处理完成")
        
        # 验证实时性
        for i in range(len(blocks)-1):  # 除去结束消息
            if i > 0:  # 跳过第一条消息的延迟检查
                interval = receive_times[i] - receive_times[i-1]
                assert 0.08 <= interval <= 0.12, f"消息间隔异常: {interval:.3f}秒"
            
            delay = receive_times[i] - blocks[i].created_at
            assert delay < 0.02, f"消息 {i} 延迟过大: {delay:.3f}秒"
            
    finally:
        # 确保正确关闭异步生成器
        if is_async and response:
            await response._collector.aclose()
        # 清理服务资源
        service.cleanup()
        await asyncio.sleep(0)  # 确保清理完成

def test_sync_stream_blocking():
    """测试同步流处理是否会阻塞"""
    service = StreamService()
    start_time = time.time()
    response = None
    
    try:
        # 获取第一条消息
        response = service.call(message="阻塞测试")
        first_message = next(iter(response))
        
        # 验证没有完全阻塞
        elapsed = time.time() - start_time
        assert elapsed < 0.1, f"获取第一条消息耗时过长: {elapsed:.3f}秒"
        
        # 验证消息内容
        assert first_message.block_type == BlockType.START
        assert "开始处理" in first_message.content
        
    finally:
        # 清理服务资源
        service.cleanup()
