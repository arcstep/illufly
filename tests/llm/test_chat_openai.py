import pytest
import os
import json
import logging
from pathlib import Path
from illufly.llm.chat_openai import ChatOpenAI
from illufly.mq.models import StreamingBlock, BlockType
from illufly.envir import get_env

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

cache_dir = get_env("ILLUFLY_CACHE_ROOT")

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.INFO)

@pytest.fixture
async def chat_with_invalid_model():
    chat = ChatOpenAI(
        prefix="ZHIPU",
        model="zhipu-test",
        service_name="test_chat_openai",
        logger=logger,
    )
    yield chat
    await chat.stop()

@pytest.fixture
async def chat_with_invalid_api_key():
    chat = ChatOpenAI(
        prefix="ZHIPU",
        api_key="invalid_key",
        service_name="test_chat_openai",
        logger=logger,
    )
    yield chat
    await chat.stop()

@pytest.fixture
async def chat():
    chat = ChatOpenAI(
        prefix="ZHIPU",
        service_name="test_chat_openai",
        logger=logger,
    )
    yield chat
    await chat.stop()

@pytest.mark.asyncio
async def test_invalid_model(chat_with_invalid_model):
    """测试无效模型场景"""
    messages = [{"role": "user", "content": "你好"}]
    blocks = []
    async for block in chat_with_invalid_model.async_call(messages):  # 直接使用 chat 实例
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

@pytest.mark.asyncio
async def test_normal_chat(chat):
    """测试正常对话场景"""
    messages = [{"role": "user", "content": "你好"}]
    blocks = []
    async for block in chat.async_call(messages):  # 直接使用 chat 实例
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-3].block_type == BlockType.TEXT_CHUNK
    assert blocks[-2].block_type == BlockType.USAGE
    assert blocks[-1].block_type == BlockType.END


@pytest.mark.asyncio
async def test_invalid_api_key(chat_with_invalid_api_key):
    """测试无效的 API Key"""
    messages = [{"role": "user", "content": "你好"}]
    resp = chat_with_invalid_api_key.async_call(messages)
    blocks = []
    logger.warning(f"OpenAI client: {chat_with_invalid_api_key.client}, model_args: {chat_with_invalid_api_key.model_args}")
    async for block in resp:
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

