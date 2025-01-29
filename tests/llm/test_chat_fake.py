import pytest
import asyncio
import logging
from illufly.llm.chat_fake import ChatFake
from illufly.mq import BlockType
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.INFO)

@pytest.fixture
async def chat():
    """异步 fixture"""
    chat = ChatFake(
        response="Hello World!",
        sleep=0.01,
        service_name="test_chat",
        logger=logger
    )
    yield chat
    await chat.stop()

@pytest.fixture
async def chat_with_list():
    chat = ChatFake(
        response=["Response 1", "Response 2"],
        sleep=0.01,
        logger=logger
    )
    yield chat
    await chat.stop()

@pytest.mark.asyncio
async def test_chat_initialization(chat):
    """测试聊天初始化"""
    assert chat.sleep == 0.01
    assert chat.response == ["Hello World!"]

@pytest.mark.asyncio
async def test_chat_response(chat):
    """测试聊天响应"""
    events = []
    resp = chat.async_call("test prompt")
    async for event in resp:
        logger.info(f"event: {event}")
        events.append(event)

    # 重复执行        
    events = []
    resp = chat.async_call("test prompt")
    async for event in resp:
        logger.info(f"event: {event}")
        events.append(event)
        
    assert len(events) > 0
    assert events[0].block_type == BlockType.TEXT_CHUNK
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i].block_type == BlockType.TEXT_CHUNK
        assert events[i].content == char
    
    assert events[-1].block_type == BlockType.END
            
@pytest.mark.asyncio
async def test_chat_multiple_responses(chat_with_list):
    """测试多轮对话"""
    blocks = []
    resp = chat_with_list.async_call("Test prompt")
    async for block in resp:
        blocks.append(block)
    
    assert len(blocks) > 0
    assert blocks[0].block_type == BlockType.TEXT_CHUNK
    assert blocks[-1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_chat_sleep_timing(chat):
    start_time = asyncio.get_event_loop().time()
    resp = chat.async_call("test")
    async for _ in resp:
        pass
        
    end_time = asyncio.get_event_loop().time()
    expected_time = 0.01 * (len("Hello World!"))  # 每个字符的睡眠时间
    
    assert end_time - start_time >= expected_time

def test_sync_chat_response(chat):
    """测试同步聊天响应"""
    # 使用同步调用
    resp = chat.call("test prompt")
    
    # 使用 with 语句自动管理资源
    events = []
    for event in resp:
        events.append(event)

    assert len(events) > 0
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i].block_type == BlockType.TEXT_CHUNK
        assert events[i].content == char
    
    assert events[-1].block_type == BlockType.END
