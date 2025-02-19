import pytest

import logging
from illufly.community.fake import ChatFake

logger = logging.getLogger(__name__)

@pytest.fixture
async def chat_service():
    """ChatFake 服务实例"""
    service = ChatFake(
        response=["Hello", "World"],
        sleep=0.01,
    )
    return service

@pytest.mark.asyncio
async def test_chat_fake_basic(chat_service):
    """测试基本聊天功能"""
    # 发送请求并收集响应
    responses = []
    async for chunk in chat_service.generate("Test message"):
        logger.info(f"chunk: {chunk}")
        responses.append(chunk.content)
    
    # 验证响应
    assert len(responses) > 0, "应该收到响应"
    assert "".join(responses) in ["Hello", "World"], "响应内容应该匹配预设"

@pytest.mark.asyncio
async def test_chat_fake_multiple_responses(chat_service):
    """测试多个响应轮换"""
    responses1 = []
    # 第一次调用
    async for chunk in chat_service.generate("Test 1"):
        responses1.append(chunk.content)
    
    # 第二次调用
    responses2 = []
    async for chunk in chat_service.generate("Test 2"):
        responses2.append(chunk.content)
    
    # 验证响应轮换
    assert "".join(responses1) != "".join(responses2), "两次调用应该返回不同的预设响应"
