import pytest
import asyncio
import logging
from illufly.llm.chat_fake import ChatFake
from illufly.base import StreamingBlock

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
    try:
        yield chat
    finally:
        chat.cleanup()

@pytest.fixture
async def chat_with_list():
    chat = ChatFake(
        response=["Response 1", "Response 2"],
        sleep=0.1,
        logger=logger
    )
    try:
        yield chat
    finally:
        chat.cleanup()

@pytest.mark.asyncio
async def test_chat_initialization(chat):
    """测试聊天初始化"""
    assert chat.sleep == 0.1
    assert chat.response == ["Hello World!"]

@pytest.mark.asyncio
async def test_chat_response(chat):
    events = []
    async for event in await chat.async_call("test prompt"):
        logger.info(f"event: {event}")
        events.append(event)
    
    assert len(events) > 0
    assert events[0]['block_type'] == "chunk"
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i]['block_type'] == "chunk"
        assert events[i]['content'] == char
    
    assert events[-1]['block_type'] == "end"

@pytest.mark.asyncio
async def test_chat_multiple_responses(chat):
    """测试多轮对话"""
    blocks = []
    async for block in await chat.async_call("Test prompt"):
        blocks.append(block)
    
    assert len(blocks) > 0
    assert blocks[0]['block_type'] == "chunk"
    assert blocks[-1]['block_type'] == "end"

@pytest.mark.asyncio
async def test_chat_sleep_timing(chat):
    start_time = asyncio.get_event_loop().time()
        
    async for _ in await chat.async_call("test"):
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
        events = []
        async for event in await chat.async_call("test"):
            if event['block_type'] == "chunk":
                events.append(event['content'])
        chat.cleanup()
        return "".join(events)
    

@pytest.mark.asyncio
async def test_chat_default_response(chat):
    # 测试没有设置response时的默认行为
    chat = ChatFake(sleep=0.1)
    prompt = "test prompt"
    
    events = []
    async for event in await chat.async_call(prompt):
        if event['block_type'] == "chunk":
            events.append(event['content'])
    chat.cleanup()
    assert "".join(events) == f"Reply >> {prompt}" 