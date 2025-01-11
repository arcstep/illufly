import pytest
import asyncio
import json
import zmq.asyncio
import logging
from typing import List, Dict, Any, AsyncIterator
from illufly.mq.models import ServiceConfig, StreamingBlock, ConcurrencyStrategy
from illufly.mq.concurrency.async_runner import AsyncRunner
from illufly.mq.message_bus import MessageBus

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

async def request_streaming_response(
    context: zmq.asyncio.Context,
    address: str,
    service_name: str,
    session_id: str,
    prompt: str,
    message_bus: MessageBus,
    **kwargs
) -> List[Dict[str, Any]]:
    """发送请求并获取流式响应
    
    Args:
        context: ZMQ Context
        address: 服务地址
        service_name: 服务名称
        session_id: 会话ID
        prompt: 请求内容
        message_bus: 消息总线实例
        **kwargs: 额外参数
        
    Returns:
        List[Dict[str, Any]]: 响应事件列表
        
    Raises:
        RuntimeError: 处理过程中的错误
    """
    logger.debug(f"Creating request for session {session_id}")
    client = context.socket(zmq.REQ)
    client.connect(address)
    
    try:
        # 发送请求
        request = {
            "session_id": session_id,
            "prompt": prompt,
            "kwargs": kwargs
        }
        logger.debug(f"Sending request: {request}")
        await client.send_json(request)
        
        # 开始接收流式响应
        events = []
        topic = f"llm.{service_name}.{session_id}"
        async for event in message_bus.subscribe([
            topic,
            f"{topic}.complete",
            f"{topic}.error"
        ]):
            logger.debug(f"Received event: {event}")
            if "error" in event:
                raise RuntimeError(event["error"])
            elif event.get("status") == "complete":
                logger.debug("Received completion notice")
                break
            else:
                events.append(event)
        
        # 等待最终处理结果
        logger.debug("Waiting for final response")
        response = await client.recv_json()
        logger.debug(f"Received final response: {response}")
        assert response["status"] == "success"
        
        return events
        
    finally:
        logger.debug("Closing client connection")
        client.close(linger=0)

@pytest.mark.asyncio
async def test_async_runner_request_handling(config):
    """测试异步执行器的请求处理"""
    logger.info("Starting request handling test")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        events = await request_streaming_response(
            context=runner.context,
            address=config.mq_address,
            service_name=config.service_name,
            session_id="test_session",
            prompt="test prompt",
            message_bus=runner.message_bus
        )
        
        # 验证响应
        assert len(events) == 1
        assert "test prompt" in events[0]["content"]
        
    finally:
        await runner.stop()

@pytest.mark.asyncio
async def test_async_runner_concurrent_requests(config):
    """测试异步执行器的并发处理"""
    logger.info(f"Starting concurrent requests test with address: {config.mq_address}")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        # 同时发送3个请求
        logger.info("Creating concurrent requests")
        tasks = [
            request_streaming_response(
                context=runner.context,
                address=config.mq_address,
                service_name=config.service_name,
                session_id=f"session_prompt_{i}",
                prompt=f"prompt_{i}",
                message_bus=runner.message_bus
            )
            for i in range(3)
        ]
        
        logger.info("Waiting for all requests to complete")
        results = await asyncio.gather(*tasks)
        logger.info("All requests completed")
        
        # 验证所有请求的响应
        for i, events in enumerate(results):
            assert len(events) == 1
            assert f"prompt_{i}" in events[0]["content"]
            
    finally:
        await runner.stop()

@pytest.mark.asyncio
async def test_async_runner_error_handling(config):
    """测试异步执行器的错误处理"""
    logger.info("Starting error handling test")
    runner = AsyncRunner(config)
    await runner.start()
    
    try:
        # 使用统一的请求函数，预期会抛出错误
        with pytest.raises(RuntimeError) as exc_info:
            await request_streaming_response(
                context=runner.context,
                address=config.mq_address,
                service_name=config.service_name,
                session_id="error_session",
                prompt=None,  # 这应该触发错误
                message_bus=runner.message_bus
            )
            
        # 验证错误消息
        assert "Prompt cannot be None" in str(exc_info.value)
        
    finally:
        await runner.stop() 