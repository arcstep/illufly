import pytest
import asyncio
import logging
import zmq.asyncio

from illufly.llm.base import BaseStreamingService, ConcurrencyStrategy
from illufly.types import EventBlock

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockStreamingService(BaseStreamingService):
    """用于测试的具体实现类"""
    async def process_request(self, prompt: str, **kwargs):
        yield EventBlock(block_type="start", content="")
        yield EventBlock(block_type="chunk", content=f"Mock response: {prompt}")
        yield EventBlock(block_type="end", content="")

@pytest.fixture
async def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def service(event_loop):
    service = MockStreamingService(service_name="test_service")
    yield service
    await service.stop()

@pytest.fixture
def process_pool_service():
    return MockStreamingService(
        service_name="test_process_service",
        concurrency=ConcurrencyStrategy.PROCESS_POOL,
        max_workers=2
    )

@pytest.fixture
def thread_pool_service():
    return MockStreamingService(
        service_name="test_thread_service",
        concurrency=ConcurrencyStrategy.THREAD_POOL,
        max_workers=2
    )

@pytest.mark.asyncio
async def test_service_initialization(service):
    try:
        assert service.service_name == "test_service"
        assert service.concurrency == ConcurrencyStrategy.ASYNC
        assert service.executor is None
    finally:
        await service.stop()

@pytest.mark.asyncio
async def test_process_pool_initialization(event_loop):
    service = MockStreamingService(
        service_name="test_process_service",
        concurrency=ConcurrencyStrategy.PROCESS_POOL,
        max_workers=2
    )
    try:
        assert service.concurrency == ConcurrencyStrategy.PROCESS_POOL
        assert service.executor is not None
    finally:
        await service.stop()

@pytest.mark.asyncio
async def test_thread_pool_initialization(thread_pool_service):
    assert thread_pool_service.concurrency == ConcurrencyStrategy.THREAD_POOL
    assert thread_pool_service.executor is not None

@pytest.mark.asyncio
async def test_basic_streaming(service):
    events = []
    try:
        async with asyncio.timeout(5):  # 5秒超时
            async for event in service("test prompt"):
                events.append(event)
    except asyncio.TimeoutError:
        pytest.fail("Test timed out")
    
    assert len(events) == 3
    assert events[0].block_type == "start"
    assert events[1].block_type == "chunk"
    assert events[1].content == "Mock response: test prompt"
    assert events[2].block_type == "end"

@pytest.mark.asyncio
async def test_multiple_concurrent_calls(service, event_loop):
    async def make_call(prompt):
        events = []
        try:
            async for event in service(prompt):
                events.append(event)
        except Exception as e:
            pytest.fail(f"Call failed for {prompt}: {str(e)}")
        return events

    tasks = [make_call(f"prompt_{i}") for i in range(3)]
    results = await asyncio.gather(*tasks)
    
    for i, events in enumerate(results):
        assert len(events) == 3
        assert events[1].content == f"Mock response: prompt_{i}"

@pytest.mark.asyncio
async def test_service_error_handling():
    class ErrorService(BaseStreamingService):
        async def process_request(self, prompt: str, **kwargs):
            raise Exception("Test error")

    service = ErrorService()
    with pytest.raises(Exception):
        async for _ in service("test"):
            pass 