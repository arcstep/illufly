import pytest
import asyncio
from illufly.llm.fake.chat import FakeChat
from illufly.llm.base import ConcurrencyStrategy

@pytest.fixture
def chat():
    return FakeChat(
        response="Hello World!",
        sleep=0.1,
        service_name="test_chat"
    )

@pytest.fixture
def chat_with_list():
    return FakeChat(
        response=["Response 1", "Response 2"],
        sleep=0.1
    )

@pytest.mark.asyncio
async def test_chat_initialization(chat):
    assert chat.sleep == 0.1
    assert chat.response == ["Hello World!"]
    assert chat.current_response_index == 0

@pytest.mark.asyncio
async def test_chat_response(chat):
    events = []
    async for event in chat("test prompt"):
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
async def test_chat_multiple_responses(chat_with_list):
    # 第一次调用
    events1 = []
    async for event in chat_with_list("first"):
        if event.block_type == "chunk":
            events1.append(event.content)
    assert "".join(events1) == "Response 1"
    
    # 第二次调用
    events2 = []
    async for event in chat_with_list("second"):
        if event.block_type == "chunk":
            events2.append(event.content)
    assert "".join(events2) == "Response 2"
    
    # 第三次调用（应该循环回到第一个响应）
    events3 = []
    async for event in chat_with_list("third"):
        if event.block_type == "chunk":
            events3.append(event.content)
    assert "".join(events3) == "Response 1"

@pytest.mark.asyncio
async def test_chat_sleep_timing(chat):
    start_time = asyncio.get_event_loop().time()
    
    async for _ in chat("test"):
        pass
        
    end_time = asyncio.get_event_loop().time()
    expected_time = 0.1 * (len("Hello World!"))  # 每个字符的睡眠时间
    
    assert end_time - start_time >= expected_time

@pytest.mark.asyncio
async def test_chat_concurrency_modes():
    # 测试不同的并发模式
    async def test_mode(concurrency):
        chat = FakeChat(
            response="Test",
            concurrency=concurrency,
            max_workers=2
        )
        events = []
        async for event in chat("test"):
            if event.block_type == "chunk":
                events.append(event.content)
        return "".join(events)
    
    # 测试所有并发模式
    for mode in ConcurrencyStrategy:
        result = await test_mode(mode)
        assert result == "Test"

@pytest.mark.asyncio
async def test_chat_default_response(chat):
    # 测试没有设置response时的默认行为
    chat = FakeChat(sleep=0.1)
    prompt = "test prompt"
    
    events = []
    async for event in chat(prompt):
        if event.block_type == "chunk":
            events.append(event.content)
    
    assert "".join(events) == f"Reply >> {prompt}" 