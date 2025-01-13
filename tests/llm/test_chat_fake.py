import pytest
import asyncio
import logging
from illufly.llm.chat_fake import ChatFake

logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)

@pytest.fixture
async def chat():
    """异步 fixture"""
    chat = ChatFake(
        response="Hello World!",
        sleep=0.1,
        service_name="test_chat",
        logger=logger
    )
    await chat.start_async()
    try:
        yield chat
    finally:
        await chat.stop_async()

@pytest.fixture
async def chat_with_list():
    chat = ChatFake(
        response=["Response 1", "Response 2"],
        sleep=0.1,
        logger=logger
    )
    await chat.start_async()
    try:
        yield chat
    finally:
        await chat.stop_async()

@pytest.mark.asyncio
async def test_chat_initialization(chat):
    """测试聊天初始化"""
    chat_instance = await anext(chat)
    assert chat_instance._running
    assert chat_instance.sleep == 0.1
    assert chat_instance.response == ["Hello World!"]

@pytest.mark.asyncio
async def test_chat_response(chat):
    chat_instance = await anext(chat)
    events = []
    async for event in chat_instance("test prompt"):
        logger.info(f"event: {event}")
        events.append(event)
    
    assert len(events) > 0
    assert events[0].block_type == "info"
    assert events[0].content == "I am FakeLLM"
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i+1].block_type == "chunk"
        assert events[i+1].content == char
    
    assert events[-1].block_type == "end"

@pytest.mark.asyncio
async def test_chat_multiple_responses(chat):
    """测试多轮对话"""
    chat_instance = await anext(chat)
    blocks = []
    async for block in chat_instance("Test prompt"):
        blocks.append(block)
    
    assert len(blocks) > 0
    assert blocks[0].block_type == "info"
    assert blocks[-1].block_type == "end"

@pytest.mark.asyncio
async def test_chat_sleep_timing(chat):
    chat_instance = await anext(chat)
    start_time = asyncio.get_event_loop().time()
        
    async for _ in chat_instance("test"):
        pass
        
    end_time = asyncio.get_event_loop().time()
    expected_time = 0.1 * (len("Hello World!"))  # 每个字符的睡眠时间
    
    assert end_time - start_time >= expected_time

@pytest.mark.asyncio
async def test_chat_concurrency_modes():
    # 测试不同的并发模式
    async def test_mode(concurrency):
        chat = ChatFake(
            response="Test",
            concurrency=concurrency,
            max_workers=2
        )
        chat.start()
        events = []
        async for event in chat("test"):
            if event.block_type == "chunk":
                events.append(event.content)
        chat.stop()
        return "".join(events)
    

@pytest.mark.asyncio
async def test_chat_default_response(chat):
    # 测试没有设置response时的默认行为
    chat = ChatFake(sleep=0.1)
    await chat.start_async()
    prompt = "test prompt"
    
    events = []
    async for event in chat(prompt):
        if event.block_type == "chunk":
            events.append(event.content)
    await chat.stop_async()
    assert "".join(events) == f"Reply >> {prompt}" 
