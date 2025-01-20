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
def chat():
    """异步 fixture"""
    chat = ChatFake(
        response="Hello World!",
        sleep=0.1,
        service_name="test_chat",
        logger=logger
    )
    return chat

@pytest.fixture
def chat_with_list():
    chat = ChatFake(
        response=["Response 1", "Response 2"],
        sleep=0.1,
        logger=logger
    )
    return chat

@pytest.mark.asyncio
async def test_chat_initialization(chat):
    """测试聊天初始化"""
    assert chat.sleep == 0.1
    assert chat.response == ["Hello World!"]

@pytest.mark.asyncio
async def test_chat_response(chat):
    """测试聊天响应"""
    events = []
    sub = await chat.async_call("test prompt")
    response = sub.async_collect()
    async for event in response:
        logger.info(f"event: {event}")
        events.append(event)
        
    assert len(events) > 0
    assert events[0].block_type == BlockType.CHUNK
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i].block_type == BlockType.CHUNK
        assert events[i].content == char
    
    assert events[-1].block_type == BlockType.END
            
@pytest.mark.asyncio
async def test_chat_multiple_responses(chat_with_list):
    """测试多轮对话"""
    blocks = []
    sub = await chat_with_list.async_call("Test prompt")
    response = sub.async_collect()
    async for block in response:
        blocks.append(block)
    
    assert len(blocks) > 0
    assert blocks[0].block_type == BlockType.CHUNK
    assert blocks[-1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_chat_sleep_timing(chat):
    start_time = asyncio.get_event_loop().time()
    sub = await chat.async_call("test")
    response = sub.async_collect()
    async for _ in response:
        pass
        
    end_time = asyncio.get_event_loop().time()
    expected_time = 0.1 * (len("Hello World!"))  # 每个字符的睡眠时间
    
    assert end_time - start_time >= expected_time

def test_sync_chat_response(chat):
    """测试同步聊天响应"""
    # 使用同步调用
    sub = chat.call("test prompt")
    
    # 使用 with 语句自动管理资源
    events = []
    for event in sub.collect():
        events.append(event)

    assert len(events) > 0

    # 重复收集
    events = []
    for event in sub.collect():
        events.append(event)

    assert len(events) > 0
    assert events[0].block_type == BlockType.CHUNK
    
    # 验证每个字符都是单独的chunk
    for i, char in enumerate("Hello World!"):
        assert events[i].block_type == BlockType.CHUNK
        assert events[i].content == char
    
    assert events[-1].block_type == BlockType.END
