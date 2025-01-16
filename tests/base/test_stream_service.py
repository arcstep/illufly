import pytest
import asyncio
import time
from illufly.base.base_service import BaseService
from illufly.mq.message_bus import MessageBus

class StreamService(BaseService):
    """用于测试的流处理服务"""
    def __init__(self, service_name: str = "stream_service", message_bus_address: str = None):
        super().__init__(service_name, message_bus_address)
        self.register_method("server", async_handle=self._stream_handler)
    
    async def _stream_handler(self, message: str, thread_id: str, message_bus: MessageBus):
        """模拟流式处理
        
        发送4条消息：
        1. 开始处理
        2-4. 处理块1-3
        """
        # 发送开始消息
        message_bus.publish(thread_id, {
            "status": "processing",
            "message": f"开始处理: {message}",
            "publish_time": time.time()
        })
        
        # 发送3个处理块
        for i in range(3):
            await asyncio.sleep(0.1)  # 模拟处理时间
            message_bus.publish(thread_id, {
                "status": "processing",
                "message": f"处理块 {i+1}: {message}",
                "progress": (i + 1) * 33,
                "publish_time": time.time()
            })
        
        # 不再发送完成和结束消息，由 BaseService 处理

@pytest.mark.parametrize("is_async", [True, False])
@pytest.mark.asyncio
async def test_stream_processing(is_async):
    """测试流处理的实时性"""
    service = StreamService()
    messages = []
    receive_times = []
    
    if is_async:
        response = await service.async_call(message="流处理测试")
        async for msg in response:
            messages.append(msg)
            receive_times.append(time.time())
            if msg.get("block_type") == "end":
                break
    else:
        response = service.call(message="流处理测试")
        for msg in response:
            messages.append(msg)
            receive_times.append(time.time())
            if msg.get("block_type") == "end":
                break
    
    # 基本验证
    assert len(messages) == 5, "应该收到5条消息"  # 开始 + 3个块 + 结束
    
    # 验证消息顺序
    assert messages[0]["status"] == "processing" and "开始处理" in messages[0]["message"]
    for i in range(1, 4):
        assert messages[i]["status"] == "processing"
        assert f"处理块 {i}" in messages[i]["message"]
        assert messages[i]["progress"] == i * 33
    assert messages[4]["block_type"] == "end"
    
    # 验证实时性
    for i, msg in enumerate(messages[:-1]):  # 除去结束标记
        delay = receive_times[i] - msg["publish_time"]
        assert delay < 0.02, f"消息 {i} 延迟过大: {delay:.3f}秒"

def test_sync_stream_blocking():
    """测试同步流处理是否会阻塞"""
    service = StreamService()
    start_time = time.time()
    
    # 获取第一条消息
    response = service.call(message="阻塞测试")
    first_message = next(iter(response))
    
    # 验证没有完全阻塞
    elapsed = time.time() - start_time
    assert elapsed < 0.1, f"获取第一条消息耗时过长: {elapsed:.3f}秒"
    
    # 验证消息内容
    assert first_message["status"] == "processing"
    assert "开始处理" in first_message["message"]