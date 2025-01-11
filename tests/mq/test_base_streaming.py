import pytest
import asyncio
import logging
from typing import AsyncIterator
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

class FakeServivce(BaseStreamingService):
    """用于测试的具体服务实现"""
    async def process_request(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        """简单的测试实现"""
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

@pytest.fixture
def config():
    """测试配置"""
    return ServiceConfig(
        service_name="test_streaming",
        mq_address="ipc:///tmp/test_streaming"
    )

@pytest.mark.asyncio
async def test_service_lifecycle(config):
    """测试服务的生命周期管理"""
    service = FakeServivce(config, logger=logger)
    assert not service._running
    
    # 启动服务
    await service.start()
    assert service._running
    assert service.runner is not None
    
    # 停止服务
    await service.stop()
    assert not service._running
    assert service.runner is not None  # runner 实例保留

@pytest.mark.asyncio
async def test_service_streaming_response(config):
    """测试服务的流式响应"""
    service = FakeServivce(config, logger=logger)
    await service.start()
    
    try:
        # 收集响应
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        # 验证响应
        assert len(blocks) == 1
        assert blocks[0].content == "Test response for: test prompt"
        assert blocks[0].block_type == "text"
        
    finally:
        await service.stop()

@pytest.mark.asyncio
async def test_service_concurrent_requests(config):
    """测试服务的并发请求处理"""
    service = FakeServivce(config, logger=logger)
    await service.start()
    
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
        await service.stop()

@pytest.mark.asyncio
async def test_service_error_handling(config):
    """测试服务的错误处理"""
    service = FakeServivce(config, logger=logger)
    
    # 测试未启动状态调用
    with pytest.raises(RuntimeError) as exc_info:
        async for _ in service("test"):
            pass
    assert "Service not started" in str(exc_info.value)
    
    # 启动服务后测试
    await service.start()
    try:
        # 测试空输入
        with pytest.raises(ValueError) as exc_info:
            async for _ in service(""):
                pass
        assert "Prompt cannot be Empty" in str(exc_info.value)
        
        # 测试None输入
        with pytest.raises(ValueError) as exc_info:
            async for _ in service(None):  # type: ignore
                pass
        assert "Prompt cannot be Empty" in str(exc_info.value)
        
    finally:
        await service.stop()

@pytest.mark.asyncio
async def test_service_cleanup(config):
    """测试服务的资源清理"""
    service = FakeServivce(config, logger=logger)
    await service.start()
    
    # 模拟服务异常停止
    await service.stop()
    
    # 验证重新启动
    await service.start()
    try:
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
        
        assert len(blocks) == 1
        assert "test prompt" in blocks[0].content
        
    finally:
        await service.stop()