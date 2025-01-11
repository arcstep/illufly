import pytest
import asyncio
import logging
from illufly.mq.message_bus import MessageBus
from illufly.mq.base_streaming import BaseStreamingService, ConcurrencyStrategy
from illufly.types import EventBlock

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class MockStreamingService(BaseStreamingService):
    """模拟的流式服务"""
    async def process_request(self, prompt: str, **kwargs):
        """处理请求的具体实现"""
        # 移除所有实例属性，只保留必要的处理逻辑
        yield EventBlock(block_type="start", content="")
        yield EventBlock(block_type="chunk", content=f"Mock response: {prompt}")
        yield EventBlock(block_type="end", content="")

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)

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
    """测试消息总线的单例性"""
    service1 = MockStreamingService("test_service1")
    service2 = MockStreamingService("test_service2")
    
    # 只启动服务1，不启动服务2的异步任务
    service1._initialize_resources()
    service2._initialize_resources()
    
    try:
        # 验证两个服务使用相同的消息总线地址
        assert service1.message_bus.address == service2.message_bus.address
    finally:
        # 清理资源
        service1.message_bus.cleanup()

@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [
    ConcurrencyStrategy.ASYNC,
    ConcurrencyStrategy.THREAD_POOL,
    ConcurrencyStrategy.PROCESS_POOL
])
async def test_concurrency_modes(concurrency):
    """测试不同的并发模式"""
    # 确保清理之前的资源
    MessageBus._instance = None
    MessageBus._context = None
    MessageBus._pub_socket = None
    MessageBus._started = False
    
    service = None
    try:
        service = MockStreamingService(
            service_name=f"test_{concurrency.value}",
            concurrency=concurrency,
            max_workers=2
        )
        service.start()
        
        async def client_call(prompt: str):
            events = []
            async for event in service(prompt):
                events.append(event)
                if event.block_type == "end":
                    break
            return events
        
        # 同时发送3个请求
        tasks = [
            client_call(f"prompt_{i}") 
            for i in range(3)
        ]
        results = await asyncio.gather(*tasks)
        
        # 验证每个请求的响应
        for i, events in enumerate(results):
            assert len(events) == 3, f"Wrong number of events for {concurrency.value}"
            assert events[0].block_type == "start"
            assert events[1].block_type == "chunk"
            assert events[1].content == f"Mock response: prompt_{i}"
            assert events[2].block_type == "end"
            
    except Exception as e:
        logging.error(f"Test failed: {str(e)}")
        raise
    finally:
        if service:
            try:
                await service.stop()
            except Exception as e:
                logging.error(f"Failed to stop service: {str(e)}")
        MessageBus.release()

@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [
    ConcurrencyStrategy.ASYNC,
    ConcurrencyStrategy.THREAD_POOL,
    ConcurrencyStrategy.PROCESS_POOL
])
async def test_heavy_load(concurrency):
    """测试高负载情况"""
    service = MockStreamingService(
        service_name=f"test_load_{concurrency.value}",
        concurrency=concurrency,
        max_workers=4
    )
    service.start()
    
    try:
        async def client_call(prompt: str):
            events = []
            async for event in service(prompt):
                events.append(event)
                if event.block_type == "end":
                    break
            return prompt, events
        
        # 模拟10个并发请求
        prompts = [f"heavy_prompt_{i}" for i in range(10)]
        tasks = [client_call(prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        
        # 验证所有请求都得到正确响应
        for prompt, events in results:
            assert len(events) == 3
            assert events[1].content == f"Mock response: {prompt}"
            
    finally:
        await service.stop()
        MessageBus.release()

@pytest.mark.asyncio
@pytest.mark.parametrize("concurrency", [
    ConcurrencyStrategy.ASYNC,
    ConcurrencyStrategy.THREAD_POOL,
    ConcurrencyStrategy.PROCESS_POOL
])
async def test_error_handling(concurrency):
    """测试错误处理"""
    class ErrorMockService(MockStreamingService):
        async def process_request(self, prompt: str, **kwargs):
            if "error" in prompt:
                raise ValueError("Test error")
            yield EventBlock(block_type="start", content="")
            yield EventBlock(block_type="end", content="")
    
    service = ErrorMockService(
        service_name=f"test_error_{concurrency.value}",
        concurrency=concurrency
    )
    service.start()
    
    try:
        # 测试正常请求
        events = []
        async for event in service("normal"):
            events.append(event)
        assert len(events) == 2
        
        # 测试错误请求
        with pytest.raises(Exception) as exc_info:
            async for event in service("trigger_error"):
                events.append(event)
        assert "Test error" in str(exc_info.value)
        
    finally:
        await service.stop()
        MessageBus.release() 
