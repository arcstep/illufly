import pytest
import asyncio
import logging
import uuid

from typing import AsyncIterator, Iterator, Any
from illufly.mq.message_bus import MessageBus
from illufly.mq.base_streaming import BaseStreamingService, ConcurrencyStrategy
from illufly.types import EventBlock
from illufly.mq.models import ServiceConfig, StreamingBlock

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)

class SyncReturnService(BaseStreamingService):
    """同步返回值实现"""
    def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class SyncGeneratorService(BaseStreamingService):
    """同步生成器实现"""
    def process(self, prompt: str, **kwargs) -> Iterator[StreamingBlock]:
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class AsyncReturnService(BaseStreamingService):
    """异步返回值实现"""
    async def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class AsyncGeneratorService(BaseStreamingService):
    """异步生成器实现"""
    async def process(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

@pytest.fixture
def service_config():
    """测试配置"""
    return ServiceConfig(
        service_name="test_streaming",
        mq_address="ipc:///tmp/test_streaming",
        concurrency=ConcurrencyStrategy.THREAD_POOL
    )

@pytest.mark.asyncio
async def test_service_lifecycle(service_config):
    """测试服务的生命周期管理"""
    service = AsyncGeneratorService(service_config, logger=logger)
    assert not service._running
    
    # 启动服务
    await service.start_async()
    assert service._running
    assert service.runner is not None
    
    # 停止服务
    await service.stop_async()
    assert not service._running
    assert service.runner is not None  # runner 实例保留

@pytest.mark.asyncio
async def test_service_concurrent_requests(service_config):
    """测试服务的并发请求处理"""
    service = AsyncGeneratorService(service_config, logger=logger)
    await service.start_async()
    
    try:
        async def make_request(i: int):
            blocks = []
            async for block in service(f"prompt_{i}"):
                blocks.append(block)
            return blocks
        
        # 同时发送3个请求
        tasks = [
            make_request(i)
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 验证所有请求的响应
        for i, blocks in enumerate(results):
            assert len(blocks) == 1
            assert blocks[0].content == f"Test response for: prompt_{i}"
            assert blocks[0].block_type == "text"
            
    finally:
        await service.stop_async()
