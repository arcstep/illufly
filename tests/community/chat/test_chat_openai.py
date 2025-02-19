import pytest

import logging
from illufly.community.openai import ChatOpenAI
from illufly.mq.models import BlockType, ToolCallChunk, ToolCallFinal
from illufly.community.base_tool import BaseTool, ToolCallMessage

logger = logging.getLogger(__name__)

@pytest.fixture
async def chat_service():
    """ChatFake 服务实例"""
    service = ChatOpenAI(
        model="gpt-4o-mini",
        imitator="OPENAI",
    )
    return service

@pytest.mark.asyncio
async def test_chat_basic(chat_service):
    """测试基本聊天功能"""
    # 发送请求并收集响应
    chunks = []
    final_text = ""
    async for chunk in chat_service.generate(messages=[{"role": "user", "content": "请跟我重复一遍：我很棒"}]):
        logger.info(f"[{chunk.block_type}] {chunk.content}")
        chunks.append(chunk)
        if chunk.block_type == BlockType.TEXT_FINAL:
            final_text = chunk.content    
    # 验证响应
    assert len(chunks) > 0, "应该收到响应"
    assert "我很棒" in final_text, "响应内容应该匹配预设"

