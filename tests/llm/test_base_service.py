import pytest
import asyncio
import logging
from illufly.llm.base import BaseStreamingService, ConcurrencyStrategy, MessageBus
from illufly.types import EventBlock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockStreamingService(BaseStreamingService):
    """用于测试的具体实现类"""
    async def process_request(self, prompt: str, **kwargs):
        """服务端处理逻辑"""
        yield EventBlock(block_type="start", content="")
        yield EventBlock(block_type="chunk", content=f"Mock response: {prompt}")
        yield EventBlock(block_type="end", content="")

@pytest.fixture
async def service():
    """服务 fixture"""
    # 确保清理之前的资源
    MessageBus._instance = None
    MessageBus._context = None
    MessageBus._pub_socket = None
    
    # 创建新的服务实例
    service = MockStreamingService(service_name="test_service")
    service.start()
    
    try:
        yield service
    finally:
        # 确保服务端正确停止
        await service.stop()

@pytest.mark.asyncio
async def test_basic_streaming(service):
    """测试基本的流式响应"""
    events = []
    try:
        # 作为客户端调用服务
        async for event in service("test prompt"):
            events.append(event)
            if event.block_type == "end":
                break
    except Exception as e:
        pytest.fail(f"Test failed: {str(e)}")

    # 验证响应
    assert len(events) == 3
    assert events[0].block_type == "start"
    assert events[1].block_type == "chunk"
    assert events[1].content == "Mock response: test prompt"
    assert events[2].block_type == "end"

@pytest.mark.asyncio
async def test_multiple_clients(service):
    """测试多客户端并发访问"""
    async def client_call(prompt: str):
        events = []
        async for event in service(prompt):
            events.append(event)
            if event.block_type == "end":
                break
        return events

    # 并发执行多个客户端请求
    tasks = [
        client_call(f"prompt_{i}") 
        for i in range(3)
    ]
    results = await asyncio.gather(*tasks)

    # 验证每个客户端的响应
    for i, events in enumerate(results):
        assert len(events) == 3
        assert events[1].content == f"Mock response: prompt_{i}"

@pytest.mark.asyncio
async def test_message_bus_singleton():
    """测试消息总线是否为单例"""
    service1 = MockStreamingService(service_name="service1")
    service2 = MockStreamingService(service_name="service2")
    
    # 验证两个服务使用相同的消息总线实例
    assert service1.message_bus is service2.message_bus
    
    # 验证消息总线地址相同
    assert service1.message_bus.address == service2.message_bus.address
    
    # 验证 PUB socket 是同一个
    assert service1.message_bus.socket is service2.message_bus.socket 
