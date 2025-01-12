import pytest
import logging
import asyncio
import zmq.asyncio
from typing import AsyncIterator
from illufly.mq.models import ServiceConfig, StreamingBlock, ConcurrencyStrategy
from illufly.mq.concurrency.thread_runner import ThreadRunner
from illufly.mq.base_streaming import BaseStreamingService, request_streaming_response

logger = logging.getLogger(__name__)

class AsyncGeneratorService(BaseStreamingService):
    """异步生成器实现"""
    async def process(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        self._logger.info(f"开始处理请求: {prompt}")
        # 增加处理延迟，强制使用多个线程
        await asyncio.sleep(1.0)
        block = StreamingBlock(
            content=f"Processing: {prompt}",
            block_type="text"
        )
        self._logger.info(f"生成第一个块: {block}")
        yield block
        
        await asyncio.sleep(1.0)
        block = StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )
        self._logger.info(f"生成第二个块: {block}")
        yield block

@pytest.fixture
def config():
    """测试配置"""
    return ServiceConfig(
        service_name="test_thread_runner",
        mq_address="ipc:///tmp/test_thread_runner",
        concurrency=ConcurrencyStrategy.THREAD_POOL
    )

@pytest.fixture
async def runner(config):
    """测试运行器"""
    runner = ThreadRunner(config)
    runner.service = AsyncGeneratorService(config)
    await runner.start_async()
    yield runner
    await runner.stop_async()

@pytest.mark.asyncio
async def test_thread_pool_request_handling(runner):
    """测试线程池请求处理"""
    context = zmq.asyncio.Context.instance()
    thread_ids = set()
    
    async def make_request(i: int):
        blocks = []
        logger.info(f"开始请求 {i} 的消息接收")
        async for block in request_streaming_response(
            context=context,
            address=runner.config.mq_address,
            service_name=runner.config.service_name,
            prompt=f"test_{i}",
            logger=logger
        ):
            logger.info(f"请求 {i} 收到块: {block}")
            blocks.append(block)
            if block.thread_id:
                thread_ids.add(block.thread_id)
                logger.debug(f"收集到线程ID: {block.thread_id}")
        logger.info(f"请求 {i} 接收完成")
        return blocks
    
    # 创建多个并发请求任务
    tasks = [make_request(i) for i in range(5)]
    
    # 等待所有请求完成
    results = await asyncio.gather(*tasks)
    
    # 验证每个请求的响应
    for i, blocks in enumerate(results):
        assert len(blocks) == 2  # 每个请求应该有两个响应块
        assert blocks[0].content == f"Processing: test_{i}"
        assert blocks[1].content == f"Test response for: test_{i}"
        assert blocks[0].block_type == "text"
        assert blocks[1].block_type == "text"
    
    # 验证是否使用了多个线程
    assert len(thread_ids) > 1, f"应该使用多个线程，但只使用了: {thread_ids}"
