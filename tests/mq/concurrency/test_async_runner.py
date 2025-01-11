import pytest
import asyncio
import json
import zmq.asyncio
import logging
from typing import List, Dict, Any, AsyncIterator
from illufly.mq.models import ServiceConfig, StreamingBlock, ConcurrencyStrategy
from illufly.mq.concurrency.async_runner import AsyncRunner
from illufly.mq.message_bus import MessageBus
from illufly.mq.base_streaming import request_streaming_response

# 正确配置 logger
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logger(caplog):
    caplog.set_level(logging.DEBUG)

@pytest.fixture
def config(request):
    """为每个测试提供不同地址的配置"""
    addr = f"inproc://test_{request.function.__name__}"
    logger.info(f"Creating config with address: {addr}")
    return ServiceConfig(
        service_name="test_async",
        concurrency=ConcurrencyStrategy.ASYNC,
        mq_address=addr
    )

@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """确保每个测试后清理资源"""
    yield
    # 清理消息总线
    MessageBus.release()
    # 等待一小段时间确保资源释放
    await asyncio.sleep(0.1)

@pytest.mark.asyncio
async def test_async_runner_lifecycle(config):
    """测试异步执行器的生命周期"""
    runner = AsyncRunner(config, logger=logger)
    
    # 测试启动
    assert not runner._running
    await runner.start()
    assert runner._running
    assert runner._server_task is not None
    assert runner.context is not None
    assert runner.message_bus is not None
    
    # 测试停止
    await runner.stop()
    assert not runner._running
    assert runner._server_task.cancelled()

@pytest.mark.asyncio
async def test_async_runner_request_handling(config):
    """测试异步执行器的请求处理"""
    logger.info("Starting request handling test")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        events = []
        message_bus = MessageBus.instance()
        client = runner.context.socket(zmq.REQ)
        client.connect(config.mq_address)
        
        # 第一阶段：初始化会话
        logger.info("Phase 1: Initializing session")
        await client.send_json({"command": "init"})
        init_response = await client.recv_json()
        logger.info(f"Init response received: {init_response}")
        assert init_response["status"] == "success"
        
        session_id = init_response["session_id"]
        topic = init_response["topic"]
        
        # 创建订阅
        logger.info(f"Creating subscription for topic: {topic}")
        subscription = message_bus.subscribe([
            topic,
            f"{topic}.complete",
            f"{topic}.error"
        ])
        
        # 第二阶段：发送实际请求
        logger.info("Phase 2: Sending process request")
        request = {
            "command": "process",
            "session_id": session_id,
            "prompt": "test prompt",
            "kwargs": {}
        }
        await client.send_json(request)
        
        # 接收流式响应
        logger.info("Waiting for streaming responses")
        async for event in subscription:
            logger.info(f"Received event: {event}")
            if "error" in event:
                raise RuntimeError(event["error"])
            elif event.get("status") == "complete":
                logger.info("Received completion notice")
                break
            else:
                events.append(event)
        
        # 等待最终处理结果
        logger.info("Waiting for final response")
        response = await client.recv_json()
        logger.info(f"Final response received: {response}")
        assert response["status"] == "success"
        
        # 验证结果
        assert len(events) == 1
        assert "test prompt" in events[0]["content"]
        
    finally:
        logger.info("Cleaning up test resources")
        client.close()
        await runner.stop()

@pytest.mark.asyncio
async def test_async_runner_concurrent_requests(config):
    """测试异步执行器的并发处理"""
    logger.info(f"Starting concurrent requests test with address: {config.mq_address}")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        async def collect_responses(i: int) -> List[StreamingBlock]:
            """收集单个请求的所有响应"""
            blocks = []
            async for block in request_streaming_response(
                context=runner.context,
                address=config.mq_address,
                service_name=config.service_name,
                session_id=f"session_prompt_{i}",
                prompt=f"prompt_{i}",
            ):
                blocks.append(block)
            return blocks
            
        # 同时发送3个请求
        logger.info("Creating concurrent requests")
        tasks = [
            collect_responses(i)
            for i in range(3)
        ]
        
        logger.info("Waiting for all requests to complete")
        results = await asyncio.gather(*tasks)
        
        # 验证所有请求的响应
        for i, blocks in enumerate(results):
            assert len(blocks) == 1
            assert f"prompt_{i}" in blocks[0].content
            
    finally:
        await runner.stop()

@pytest.mark.asyncio
async def test_async_runner_error_handling(config):
    """测试异步执行器的错误处理"""
    logger.info("Starting error handling test")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        message_bus = MessageBus.instance()
        client = runner.context.socket(zmq.REQ)
        client.connect(config.mq_address)
        
        # 第一阶段：初始化会话
        logger.debug("Initializing session")
        await client.send_json({"command": "init"})
        init_response = await client.recv_json()
        assert init_response["status"] == "success"
        
        session_id = init_response["session_id"]
        topic = init_response["topic"]
        
        # 创建订阅
        logger.debug(f"Creating subscription for topic: {topic}")
        subscription = message_bus.subscribe([
            topic,
            f"{topic}.complete",
            f"{topic}.error"
        ])
        
        # 第二阶段：发送错误请求
        request = {
            "command": "process",
            "session_id": session_id,
            "prompt": None,  # 这会触发错误
            "kwargs": {}
        }
        logger.debug(f"Sending process request: {request}")
        await client.send_json(request)
        
        # 等待错误响应
        response = await client.recv_json()
        assert response["status"] == "error"
        assert "Prompt cannot be None" in response["error"]
        
    finally:
        client.close()
        await runner.stop() 