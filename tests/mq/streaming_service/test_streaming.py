import pytest
import asyncio
import logging
import uuid
import os

from typing import AsyncIterator, Iterator, Any, Dict
from illufly.mq.streaming import StreamingService
from illufly.types import EventBlock
from illufly.mq.models import ServiceConfig, StreamingBlock

logger = logging.getLogger(__name__)

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
