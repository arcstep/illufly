import pytest
import logging
import asyncio
import multiprocessing
from typing import AsyncIterator
import zmq.asyncio
from illufly.mq.models import ServiceConfig, StreamingBlock, ConcurrencyStrategy
from illufly.mq.concurrency.process_runner import ProcessRunner
from illufly.mq.base_streaming import BaseStreamingService, request_streaming_response

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AsyncGeneratorService(BaseStreamingService):
    """异步生成器实现"""
    async def process(self, prompt: str, **kwargs) -> AsyncIterator[StreamingBlock]:
        # 增加更长的处理延迟，强制使用多个进程
        await asyncio.sleep(0.3)  # 增加到1秒
        yield StreamingBlock(
            content=f"Processing: {prompt}",
            block_type="text"
        )
        await asyncio.sleep(0.3) 
        yield StreamingBlock(
            content=f"Test response for: {prompt}",
            block_type="text"
        )

@pytest.fixture
def config():
    """测试配置"""
    return ServiceConfig(
        service_name="test_process_runner",
        mq_address="ipc:///tmp/test_process_runner",
        concurrency=ConcurrencyStrategy.PROCESS_POOL
    )

@pytest.fixture
async def runner(config):
    """测试运行器"""
    runner = ProcessRunner(config)
    runner.service = AsyncGeneratorService(config)
    await runner.start_async()
    yield runner
    await runner.stop_async()

@pytest.mark.asyncio
async def test_process_pool_request_handling(runner):
    """测试进程池请求处理"""
    context = zmq.asyncio.Context.instance()
    process_ids = set()
    
    async def make_request(i: int):
        blocks = []
        async for block in request_streaming_response(
            context=context,
            address=runner.config.mq_address,
            service_name=runner.config.service_name,
            prompt=f"test_{i}",
            logger=logger
        ):
            blocks.append(block)
            # 从原始消息中获取 process_id
            if block.process_id:  # 使用新增的字段
                process_ids.add(block.process_id)
                logger.debug(f"收集到进程ID: {block.process_id}")  # 添加调试日志
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
    
    # 验证是否使用了多个进程
    assert len(process_ids) > 1, f"应该使用多个进程，但只使用了: {process_ids}"

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)
