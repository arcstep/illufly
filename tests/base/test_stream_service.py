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
        """模拟一个长时间运行的流处理服务"""
        # 记录并发送第一个响应
        publish_times = []
        publish_times.append(time.time())
        message_bus.publish(thread_id, {
            "status": "processing",
            "message": f"开始处理: {message}",
            "publish_time": publish_times[-1]
        })
        
        # 模拟处理多个数据块
        for i in range(3):
            await asyncio.sleep(0.1)  # 模拟处理时间
            publish_times.append(time.time())
            message_bus.publish(thread_id, {
                "status": "processing",
                "message": f"处理块 {i+1}: {message}",
                "progress": (i + 1) * 33,
                "publish_time": publish_times[-1]
            })
        
        # 发送最后一条消息
        publish_times.append(time.time())
        message_bus.publish(thread_id, {
            "status": "completed",
            "message": f"处理完成: {message}",
            "block_type": "end",
            "publish_time": publish_times[-1]
        })
        
        return {"status": "success", "publish_times": publish_times}

@pytest.mark.parametrize("is_async", [True, False])
@pytest.mark.asyncio
async def test_stream_processing(is_async):
    """测试流处理的实时性
    
    验证：
    1. 消息是否按发布顺序接收
    2. 从发布到接收的延迟
    3. 是否实现了真正的流式处理
    
    Args:
        is_async: 是否使用异步调用
    """
    service = StreamService()
    messages = []
    receive_times = []
    
    # 开始收集消息
    collection_start = time.time()
    
    if is_async:
        response = await service.async_call(message="流处理测试")
        async for msg in response:
            messages.append(msg)
            receive_times.append(time.time())
    else:
        response = service.call(message="流处理测试")
        for msg in response:
            messages.append(msg)
            receive_times.append(time.time())
    
    # 基本验证
    assert len(messages) == 5, "应该收到5条消息"
    assert messages[0]["status"] == "processing"
    assert messages[-1]["block_type"] == "end"
    
    # 验证消息顺序和延迟
    for i, (msg, receive_time) in enumerate(zip(messages, receive_times)):
        # 获取发布时间
        publish_time = msg["publish_time"]
        delay = receive_time - publish_time
        
        # 验证延迟不超过合理范围 (例如 50ms)
        assert delay >= 0, f"消息 {i} 的接收时间早于发布时间"
        assert delay < 0.05, f"消息 {i} 的延迟过大: {delay:.3f}秒"
        
        if i > 0:
            # 验证消息是否按顺序发布
            assert publish_time > messages[i-1]["publish_time"], \
                f"消息 {i} 的发布顺序错误"
            
            # 验证发布间隔是否符合预期
            publish_interval = publish_time - messages[i-1]["publish_time"]
            if i < len(messages) - 1:  # 不是最后一条消息
                assert 0.08 <= publish_interval <= 0.12, \
                    f"消息 {i} 的发布间隔不符合预期: {publish_interval:.3f}秒"

def test_sync_stream_blocking():
    """测试同步流处理是否会阻塞"""
    service = StreamService()
    start_time = time.time()
    
    # 只获取第一条消息
    first_message = next(service.call(message="阻塞测试"))
    first_message_delay = time.time() - first_message["publish_time"]
    
    # 验证获取第一条消息不会等待后续消息
    assert first_message_delay < 0.05, \
        f"获取第一条消息延迟过大: {first_message_delay:.3f}秒"
    assert first_message["status"] == "processing"
    assert first_message["message"].startswith("开始处理")