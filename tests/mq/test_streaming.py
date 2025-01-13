import pytest
import asyncio
import logging
import uuid
import os

from typing import AsyncIterator, Iterator, Any, Dict
from illufly.mq.streaming import StreamingService
from illufly.types import EventBlock
from illufly.mq.models import ServiceConfig, StreamingBlock

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)

class TextReturnService(StreamingService):
    """同步返回值实现"""
    def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return f"Test response for: {prompt}"

class DictReturnService(StreamingService):
    """同步返回值实现"""
    def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return {"myreplay": "Test response for:hello", "myname": "illufly"}

class SyncReturnService(StreamingService):
    """同步返回值实现"""
    def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class SyncGeneratorService(StreamingService):
    """同步生成器实现"""
    def process(self, prompt: str, **kwargs) -> Iterator[StreamingBlock]:
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class AsyncReturnService(StreamingService):
    """异步返回值实现"""
    async def process(self, prompt: str, **kwargs) -> StreamingBlock:
        return StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class AsyncGeneratorService(StreamingService):
    """异步生成器实现"""
    async def process(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

class DictInputService(StreamingService):
    """同步返回值实现"""
    def process(self, prompt: Dict[str, str], **kwargs) -> StreamingBlock:
        name = prompt["name"]
        age = prompt["age"]
        return StreamingBlock(
            content=f"Test response for: {name} {age}",
            block_type="text"
        )

@pytest.mark.asyncio
async def test_service_lifecycle():
    """测试服务的生命周期管理"""
    service_name = f"test_service_{uuid.uuid4()}"
    config = ServiceConfig(service_name=service_name)
    
    service = AsyncGeneratorService(
        service_config=config,
        logger=logger
    )
    
    try:
        await service.start_async()
        assert service._running
        
        # 等待服务就绪
        await service._bind_event.wait()
        
    finally:
        await service.stop_async()

def test_sync_service_streaming_response():
    """同步版本：测试服务的流式响应"""
    service = SyncGeneratorService(logger=logger)
    service.start()
    
    try:
        # 收集响应
        blocks = []
        for block in service("test prompt"):
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        # 验证响应
        assert len(blocks) == 2
        assert blocks[0].content == "Test response for: test prompt"
        assert blocks[0].block_type == "chunk"
        
    finally:
        service.stop()

@pytest.mark.asyncio
async def test_service_streaming_response():
    """异步版本：测试服务的流式响应"""
    service = AsyncGeneratorService(logger=logger)
    await service.start_async()
    
    try:
        # 收集响应
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        # 验证响应
        assert len(blocks) == 2
        assert blocks[0].content == "Test response for: test prompt"
        assert blocks[0].block_type == "chunk"
        
    finally:
        await service.stop_async()

@pytest.mark.asyncio
async def test_service_dict_input_streaming_response():
    """异步版本：测试服务的流式响应"""
    service = DictInputService(logger=logger)
    await service.start_async()
    
    try:
        # 收集响应
        blocks = []
        async for block in service({"name": "illufly", "age": 18}):
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        # 验证响应
        assert len(blocks) == 2
        assert "illufly" in blocks[0].content
        assert "18" in blocks[0].content
        assert blocks[0].block_type == "chunk"
        
    finally:
        await service.stop_async()

@pytest.mark.asyncio
async def test_service_concurrent_requests():
    """测试服务的并发请求处理"""
    service = AsyncGeneratorService(logger=logger)
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
            assert len(blocks) == 2
            assert blocks[0].content == f"Test response for: prompt_{i}"
            assert blocks[0].block_type == "chunk"
            
    finally:
        await service.stop_async()

@pytest.mark.asyncio
async def test_service_error_handling():
    """测试服务的错误处理"""
    service = AsyncGeneratorService(logger=logger)
    
    # 测试未启动状态调用
    with pytest.raises(RuntimeError) as exc_info:
        async for _ in service("test"):
            pass
    assert "Service not started" in str(exc_info.value)
    
    # 启动服务后测试
    await service.start_async()
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
        await service.stop_async()

@pytest.mark.asyncio
async def test_service_cleanup():
    """测试服务的资源清理"""
    service = AsyncGeneratorService(logger=logger)
    await service.start_async()
    
    # 模拟服务异常停止
    await service.stop_async()
    
    # 验证重新启动
    await service.start_async()
    try:
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
        
        assert len(blocks) == 2
        assert "test prompt" in blocks[0].content
        
    finally:
        await service.stop_async()

def test_service_sync_context():
    """测试同步上下文管理器"""
    with AsyncGeneratorService(logger=logger) as service:
        blocks = []
        for block in service("test prompt"):
            blocks.append(block)
            logger.info(f"Received block: {block}")
            
        assert len(blocks) == 2
        assert blocks[0].content == "Test response for: test prompt"
        assert blocks[0].block_type == "chunk"

@pytest.mark.asyncio
async def test_service_async_context():
    """测试异步上下文管理器"""
    async with AsyncGeneratorService(logger=logger) as service:
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
            logger.info(f"Received block: {block}")
            
        assert len(blocks) == 2
        assert blocks[0].content == "Test response for: test prompt"
        assert blocks[0].block_type == "chunk"

def test_service_context_error_handling():
    """测试上下文管理器的错误处理"""
    try:
        with AsyncGeneratorService(logger=logger) as service:
            for block in service(""):  # 应该抛出 ValueError
                pass
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Prompt cannot be Empty" in str(e)

@pytest.mark.asyncio
async def test_service_async_context_error_handling():
    """测试异步上下文管理器的错误处理"""
    try:
        async with AsyncGeneratorService(logger=logger) as service:
            async for block in service(""):  # 应该抛出 ValueError
                pass
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Prompt cannot be Empty" in str(e)

@pytest.mark.parametrize("service_class", [
    SyncReturnService,
    SyncGeneratorService,
    AsyncReturnService,
    AsyncGeneratorService,
    DictReturnService,
    TextReturnService
])
def test_service_implementations(service_class):
    """测试不同的实现方式"""
    service = service_class(logger=logger)
    with service:
        blocks = []
        for block in service("test prompt"):
            blocks.append(block)
            
        assert len(blocks) == 2
        assert "Test response for" in blocks[0].content
        assert blocks[0].block_type == "chunk"

@pytest.mark.parametrize("service_class", [
    SyncReturnService,
    SyncGeneratorService,
    AsyncReturnService,
    AsyncGeneratorService,
    DictReturnService,
    TextReturnService
])
@pytest.mark.asyncio
async def test_service_implementations_async(service_class):
    """测试不同的实现方式"""
    service = service_class(logger=logger)
    async with service:
        blocks = []
        async for block in service("test prompt"):
            blocks.append(block)
            
        assert len(blocks) == 2
        assert "Test response for" in blocks[0].content
        assert blocks[0].block_type == "chunk"
