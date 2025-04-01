import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any, Optional
from unittest.mock import MagicMock
from pydantic import BaseModel

from illufly.llm.chat import ChatAgent
from illufly.llm.models import ChunkType, DialougeChunk, ToolCalling
from illufly.llm.memory import Memory
from illufly.rocksdb import IndexedRocksDB
from litellm import completion


@pytest.fixture
def mock_db():
    db = Mock(spec=IndexedRocksDB)
    db.values = Mock(return_value=[])
    db.update_with_indexes = Mock()
    return db

@pytest.fixture
def mock_memory():
    memory = Mock(spec=Memory)
    memory.retrieve = AsyncMock(return_value="mock_memory")
    memory.extract = AsyncMock()
    memory.inject = Mock(return_value=[{"role": "system", "content": "注入记忆后的消息"}])
    return memory

@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.acompletion = AsyncMock()
    return llm

@pytest.fixture
def chat_agent(mock_db, mock_memory, mock_llm):
    agent = ChatAgent(db=mock_db, memory=mock_memory)
    agent.llm = mock_llm
    return agent

@pytest.mark.asyncio
async def test_chat_input_validation(chat_agent):
    """测试输入验证"""
    # 测试空消息
    with pytest.raises(ValueError, match="messages 不能为空"):
        async for _ in chat_agent.chat([]):
            pass

    # 测试无效消息格式
    with pytest.raises(ValueError, match="messages 必须是形如"):
        async for _ in chat_agent.chat({"invalid": "format"}):
            pass

    # 测试字符串消息自动转换
    async for chunk in chat_agent.chat("test message"):
        assert isinstance(chunk, dict)

@pytest.mark.asyncio
async def test_load_history_messages(chat_agent, mock_db):
    """测试加载历史消息"""
    # 模拟历史消息
    mock_history = [
        DialougeChunk(
            user_id="test_user",
            thread_id="test_thread",
            chunk_type=ChunkType.USER_INPUT,
            input_messages=[{"role": "user", "content": "历史消息1"}]
        ),
        DialougeChunk(
            user_id="test_user",
            thread_id="test_thread",
            chunk_type=ChunkType.AI_MESSAGE,
            output_text="AI回复1"
        )
    ]
    mock_db.values.return_value = mock_history

    messages = [{"role": "user", "content": "新消息"}]
    async for _ in chat_agent.chat(messages, user_id="test_user", thread_id="test_thread"):
        pass

    # 验证历史消息是否被正确加载
    mock_db.values.assert_called_once()
    # 使用正确的前缀格式
    assert mock_db.values.call_args[1]["prefix"].startswith("dlg-test_user-test_thread")
    
    # 添加更多具体的验证
    assert mock_db.values.call_args[1]["limit"] == chat_agent.recent_messages_count
    assert mock_db.values.call_args[1]["reverse"] is True

@pytest.mark.asyncio
async def test_dialog_prepare(chat_agent, mock_db, mock_memory):
    """测试对话片段保存"""
    # 准备测试数据
    system_message = {"role": "system", "content": "系统提示"}
    user_message = {"role": "user", "content": "测试消息"}
    messages = [system_message, user_message]
    
    # 模拟历史消息
    history_message = {"role": "user", "content": "历史消息"}
    mock_db.values.return_value = [
        DialougeChunk(
            user_id="test_user",
            thread_id="test_thread",
            chunk_type=ChunkType.USER_INPUT,
            input_messages=[history_message]
        )
    ]

    # 模拟记忆注入
    injected_message = {"role": "system", "content": "注入记忆后的消息"}
    mock_memory.inject.return_value = [system_message, history_message, user_message, injected_message]

    async for _ in chat_agent.chat(messages, user_id="test_user", thread_id="test_thread"):
        pass

    # 验证用户输入保存
    assert mock_db.update_with_indexes.call_count >= 1
    saved_chunks = [call[1]["value"] for call in mock_db.update_with_indexes.call_args_list]
    
    # 验证保存的用户输入包含完整的消息序列
    user_chunks = [c for c in saved_chunks if c.chunk_type == ChunkType.USER_INPUT]
    assert len(user_chunks) == 1
    saved_messages = user_chunks[0].input_messages
    
    # 验证消息顺序和内容
    assert len(saved_messages) == 4  # system + history + user + injected
    assert saved_messages[0] == system_message  # 系统消息
    assert saved_messages[1] == history_message  # 历史消息
    assert saved_messages[2] == user_message  # 用户消息
    assert saved_messages[3] == injected_message  # 注入的记忆

    # 验证记忆操作的调用顺序
    mock_memory.retrieve.assert_called_once()
    mock_memory.inject.assert_called_once()
    mock_memory.extract.assert_called_once()

@pytest.mark.asyncio
async def test_chat_completion(chat_agent, mock_llm):
    """测试对话补全"""
    # 设置 mock 响应
    mock_response = "这是一个测试回复"
    mock_llm.acompletion.return_value = completion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "test"}],
        stream=True,
        mock_response=mock_response
    )

    messages = [{"role": "user", "content": "测试消息"}]
    responses = []
    complete_response = ""
    
    async for chunk in chat_agent.chat(messages):
        responses.append(chunk)
        if "output_text" in chunk:
            complete_response += chunk["output_text"]

    # 验证响应内容
    assert len(responses) > 0
    assert complete_response == mock_response

@pytest.mark.asyncio
async def test_tool_calling(chat_agent, mock_llm):
    """测试工具调用"""
    from pydantic import BaseModel
    from typing import List, Optional, Dict, Any
    
    # 创建简单的响应模型
    class Function(BaseModel):
        name: str
        arguments: str
        
    class ToolCall(BaseModel):
        id: str
        function: Function
        
    class Delta(BaseModel):
        content: Optional[str] = None
        tool_calls: Optional[List[ToolCall]] = None
        
    class Choice(BaseModel):
        delta: Delta
        
    class Response(BaseModel):
        choices: List[Choice]
    
    async def mock_stream():
        # 使用实际数据而不是MagicMock
        mock_obj = Response(
            choices=[
                Choice(
                    delta=Delta(
                        content=None,
                        tool_calls=[
                            ToolCall(
                                id="test_tool_id",
                                function=Function(
                                    name="test_tool",
                                    arguments='{"arg": "value"}'
                                )
                            )
                        ]
                    )
                )
            ]
        )
        yield mock_obj

    # 使用异步生成器
    mock_llm.acompletion.return_value = mock_stream()

    messages = [{"role": "user", "content": "调用工具"}]
    responses = []
    async for chunk in chat_agent.chat(messages):
        responses.append(chunk)

    # 验证工具调用响应
    tool_responses = [r for r in responses if "tool_calls" in r]
    assert len(tool_responses) > 0
    assert tool_responses[0]["tool_calls"][0]["name"] == "test_tool"
    assert tool_responses[0]["tool_calls"][0]["arguments"] == '{"arg": "value"}'

def test_load_history(chat_agent, mock_db):
    """测试加载历史对话"""
    # 模拟历史对话数据
    mock_history = [
        DialougeChunk(
            user_id="test_user",
            thread_id="test_thread",
            chunk_type=ChunkType.USER_INPUT,
            input_messages=[{"role": "user", "content": "用户消息"}]
        ),
        DialougeChunk(
            user_id="test_user",
            thread_id="test_thread",
            chunk_type=ChunkType.AI_MESSAGE,
            output_text="AI回复"
        )
    ]
    mock_db.values.return_value = mock_history

    history = chat_agent.load_history("test_user", "test_thread")
    
    # 验证历史消息格式
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"