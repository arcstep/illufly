import pytest

import logging
from illufly.community.fake import ChatFake
from illufly.community.base_tool import BaseTool
from illufly.community.models import ToolCallChunk, ToolCallFinal, TextChunk, TextFinal

logger = logging.getLogger(__name__)

@pytest.fixture
async def chat_service():
    """ChatFake 服务实例"""
    service = ChatFake(
        response=["Hello", "World"],
        sleep=0.01,
    )
    return service

@pytest.fixture
def mock_tool():
    """模拟工具实例"""
    class MockTool(BaseTool):
        name = "mock_tool"
        description = "模拟工具"

        @classmethod
        async def call(cls, **kwargs):
            return "Mock tool result"

    return MockTool

@pytest.mark.asyncio
async def test_chat_fake_basic(chat_service):
    """测试基本聊天功能"""
    # 发送请求并收集响应
    chunks = []
    final_text = ""
    async for chunk in chat_service.generate("Test message"):
        logger.info(f"chunk: {chunk}")
        if isinstance(chunk, TextChunk):
            chunks.append(chunk.content)
        elif isinstance(chunk, TextFinal):
            final_text = chunk.content
    
    # 验证响应
    assert len(chunks) > 0, "应该收到响应"
    assert "".join(chunks) in ["Hello", "World"], "响应内容应该匹配预设"
    assert final_text in ["Hello", "World"], "最终响应内容应该匹配预设"

@pytest.mark.asyncio
async def test_chat_fake_multiple_responses(chat_service):
    """测试多个响应轮换"""
    responses1 = []
    # 第一次调用
    async for chunk in chat_service.generate("Test 1"):
        if isinstance(chunk, TextChunk):
            responses1.append(chunk.content)
    
    # 第二次调用
    responses2 = []
    async for chunk in chat_service.generate("Test 2"):
        if isinstance(chunk, TextChunk):
            responses2.append(chunk.content)
    
    # 验证响应轮换
    assert "".join(responses1) != "".join(responses2), "两次调用应该返回不同的预设响应"

@pytest.mark.asyncio
async def test_tool_calls():
    """测试工具调用场景"""
    fake = ChatFake(
        tool_responses=[
            {"name": "weather", "arguments": {"city": "Beijing"}},
            {"name": "calculator", "arguments": {"expression": "1+1"}}
        ]
    )
    
    # 第一次调用应返回工具调用
    chunks = []
    async for chunk in fake.generate("What's Beijing weather?", tools=[mock_tool]):
        chunks.append(chunk)
    
    assert len(chunks) == 2, "应该返回ToolCallChunk和ToolCallFinal"
    assert isinstance(chunks[0], ToolCallChunk)
    assert chunks[0].tool_name == "weather"
    
    # 发送工具结果后应得到处理后的回复
    messages = [
        {"role": "user", "content": "What's Beijing weather?"},
        {"role": "tool", "content": "Sunny"}
    ]
    responses = []
    async for chunk in fake.generate(messages):
        responses.append(chunk.content)
    
    assert "Sunny" in "".join(responses), "应处理工具结果"
