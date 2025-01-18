import pytest
import os
import json
import logging
from pathlib import Path
from illufly.llm.chat_openai import ChatOpenAI
from illufly.mq.models import StreamingBlock, BlockType

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.INFO)

@pytest.fixture
def chat_with_invalid_model(tmp_path):
    os.environ["ILLUFLY_CACHE_CALL"] = str(tmp_path / "chat_cache_1")
    return ChatOpenAI(
        prefix="QWEN",
        model="qwen-test",
        service_name="test_chat_openai",
        logger=logger,
        enable_cache=True
    )

@pytest.fixture
def chat_with_invalid_api_key(tmp_path):
    os.environ["ILLUFLY_CACHE_CALL"] = str(tmp_path / "chat_cache_2")
    return ChatOpenAI(
        prefix="QWEN",
        api_key="invalid_key",
        service_name="test_chat_openai",
        logger=logger,
        enable_cache=False
    )

@pytest.fixture
def chat(tmp_path):
    os.environ["ILLUFLY_CACHE_CALL"] = str(tmp_path / "chat_cache_2")
    return ChatOpenAI(
        prefix="QWEN",
        service_name="test_chat_openai",
        logger=logger,
        enable_cache=False
    )

def test_invalid_model(chat_with_invalid_model):
    """测试无效模型场景"""
    messages = [{"role": "user", "content": "你好"}]
    blocks = []
    for block in chat_with_invalid_model(messages):  # 直接使用 chat 实例
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

def test_normal_chat(chat):
    """测试正常对话场景"""
    messages = [{"role": "user", "content": "你好"}]
    blocks = []
    for block in chat(messages):  # 直接使用 chat 实例
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
        blocks = []
        for block in chat(messages):
            blocks.append(block)
            logger.info(f"Received block: {block}")
        
        assert blocks[-2].block_type == BlockType.ERROR
        assert blocks[-1].block_type == BlockType.END

def test_invalid_api_key(chat_with_invalid_api_key):
    """测试无效的 API Key"""
    messages = [{"role": "user", "content": "你好"}]
    blocks = []
    for block in chat_with_invalid_api_key(messages):
        blocks.append(block)
        logger.info(f"Received block: {block}")
    
    assert blocks[-2].block_type == BlockType.ERROR
    assert blocks[-1].block_type == BlockType.END

