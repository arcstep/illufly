import pytest
import pandas as pd
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict

from illufly.llm.memory import Memory, MemoryQA
from illufly.llm.base import LiteLLM
from illufly.rocksdb import IndexedRocksDB
from illufly.llm.retriever import ChromaRetriever

@pytest.fixture
def mock_llm():
    llm = Mock(spec=LiteLLM)
    llm.acompletion = AsyncMock()
    llm.acompletion.return_value.choices = [
        Mock(message=Mock(content="""
        |主题|问题|答案|
        |---|---|---|
        |测试主题|测试问题|测试答案|
        """))
    ]
    return llm

@pytest.fixture
def mock_memory_db():
    db = Mock(spec=IndexedRocksDB)
    db.values.return_value = []
    db.update_with_indexes = Mock()
    return db

@pytest.fixture
def mock_retriever():
    retriever = Mock(spec=ChromaRetriever)
    retriever.add = AsyncMock()
    retriever.query = AsyncMock()
    retriever.get_or_create_collection = Mock()
    retriever.query.return_value = [{
        "metadatas": [{"topic": "测试主题", "question": "测试问题", "answer": "测试答案"}]
    }]
    return retriever

@pytest.fixture
def memory(mock_llm, mock_memory_db, mock_retriever):
    return Memory(mock_llm, mock_memory_db, mock_retriever)

def test_from_messages_to_text(memory):
    """测试消息转换为文本"""
    input_messages = [
        {"role": "user", "content": "用户消息"},
        {"role": "assistant", "content": "助手回复"}
    ]
    
    result = memory.from_messages_to_text(input_messages)
    
    assert "user: 用户消息" in result
    assert "assistant: 助手回复" in result

def test_safe_extract_markdown_tables(memory):
    """测试安全提取Markdown表格"""
    md_text = """
    |主题|问题|答案|
    |---|---|---|
    |测试主题|测试问题|测试答案|
    """
    
    tables = memory.safe_extract_markdown_tables(md_text)
    
    assert len(tables) == 1
    assert isinstance(tables[0], pd.DataFrame)
    assert list(tables[0].columns) == ["主题", "问题", "答案"]
    assert tables[0].iloc[0]["主题"] == "测试主题"

def test_safe_extract_markdown_tables_multiple(memory):
    """测试提取多个Markdown表格"""
    md_text = """
    |主题|问题|答案|
    |---|---|---|
    |测试主题1|测试问题1|测试答案1|

    |主题|问题|答案|
    |---|---|---|
    |测试主题2|测试问题2|测试答案2|
    """
    
    tables = memory.safe_extract_markdown_tables(md_text)
    
    assert len(tables) == 2
    assert isinstance(tables[0], pd.DataFrame)
    assert isinstance(tables[1], pd.DataFrame)
    
    # 验证第一个表格
    assert tables[0].iloc[0]["主题"] == "测试主题1"
    assert tables[0].iloc[0]["问题"] == "测试问题1"
    assert tables[0].iloc[0]["答案"] == "测试答案1"
    
    # 验证第二个表格
    assert tables[1].iloc[0]["主题"] == "测试主题2"
    assert tables[1].iloc[0]["问题"] == "测试问题2"
    assert tables[1].iloc[0]["答案"] == "测试答案2"

def test_safe_extract_markdown_tables_invalid(memory):
    """测试处理无效的Markdown表格"""
    md_text = """
    无效的表格格式
    |主题|问题
    测试主题|测试问题
    """
    
    tables = memory.safe_extract_markdown_tables(md_text)
    
    assert len(tables) == 0

@pytest.mark.asyncio
async def test_init_retriever(memory):
    """测试初始化记忆检索器"""
    await memory.init_retriever()
    memory.retriver.get_or_create_collection.assert_called_once_with("memory")

@pytest.mark.asyncio
async def test_extract(memory):
    """测试提取记忆"""
    input_messages = [
        {"role": "user", "content": "测试消息"}
    ]
    
    await memory.extract(input_messages, user_id="test_user")
    
    # 验证调用
    memory.llm.acompletion.assert_called_once()
    memory.memory_db.update_with_indexes.assert_called_once()
    memory.retriver.add.assert_called_once()

@pytest.mark.asyncio
async def test_retrieve(memory):
    """测试检索记忆"""
    input_messages = [
        {"role": "user", "content": "测试消息"}
    ]
    
    result = await memory.retrieve(input_messages, user_id="test_user")
    
    assert isinstance(result, str)
    assert "测试主题" in result
    assert "测试问题" in result
    assert "测试答案" in result

def test_inject(memory):
    """测试注入记忆"""
    input_messages = [
        {"role": "system", "content": "系统消息"}
    ]
    existing_memory = "|主题|问题|答案|\n|测试主题|测试问题|测试答案|"
    
    result = memory.inject(input_messages, existing_memory)
    
    assert len(result) == 1
    assert "用户记忆清单" in result[0]["content"]
    assert existing_memory in result[0]["content"]

