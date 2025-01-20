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
def chat_with_invalid_model():
    return ChatOpenAI(
        prefix="QWEN",
        model="qwen-test",
        service_name="test_chat_openai",
        logger=logger,
    )

@pytest.fixture
def chat_with_invalid_api_key():
    return ChatOpenAI(
        prefix="QWEN",
        api_key="invalid_key",
        service_name="test_chat_openai",
        logger=logger,
    )

@pytest.fixture
def chat():
    return ChatOpenAI(
        prefix="QWEN",
        service_name="test_chat_openai",
        logger=logger,
    )

def test_invalid_model(chat_with_invalid_model):
    """测试无效模型场景"""
    messages = [{"role": "user", "content": "你好"}]
    sub = chat_with_invalid_model(messages)
    blocks = []
    for block in sub.collect():  # 直接使用 chat 实例
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

def test_normal_chat(chat):
    """测试正常对话场景"""
    messages = [{"role": "user", "content": "你好"}]
    sub = chat(messages)
    blocks = []
    for block in sub.collect():  # 直接使用 chat 实例
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.CHUNK
    assert blocks[-1].block_type == BlockType.END

def test_invalid_message_format(chat):
    """测试无效的消息格式"""
    invalid_messages = [
        "不是字典的消息",  # 不是字典
        {"missing_role": "content"},  # 缺少必要的键
        {"role": 123, "content": "内容"},  # role 不是字符串
        {"role": "user", "content": 456}  # content 不是字符串
    ]
    for message in invalid_messages:
        messages = [message]
        sub = chat(messages)
        blocks = []
        for block in sub.collect():
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        assert blocks[-2].block_type == BlockType.ERROR
        assert blocks[-1].block_type == BlockType.END

def test_invalid_api_key(chat_with_invalid_api_key):
    """测试无效的 API Key"""
    messages = [{"role": "user", "content": "你好"}]
    sub = chat_with_invalid_api_key(messages)
    blocks = []
    logger.warning(f"OpenAI client: {chat_with_invalid_api_key.client}, model_args: {chat_with_invalid_api_key.model_args}")
    for block in sub.collect():
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

