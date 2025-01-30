import pytest
from datetime import datetime
from typing import List, Dict, Any

from illufly.llm.chat_base import ChatBase
from illufly.llm.memory.L0_QA.models import Message, QA, Thread
from illufly.mq import Publisher, StreamingBlock, BlockType, TextChunk

class MockChatAgent(ChatBase):
    """模拟的聊天代理"""
    async def _async_handler(
        self,
        messages: List[Dict[str, Any]],
        publisher: Publisher,
        request_id: str,
        **kwargs
    ):
        """模拟 LLM 生成回复"""
        # 简单返回最后一条用户消息的反转字符串
        last_user_msg = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                last_user_msg = msg["content"]
                break
        return last_user_msg[::-1]  # 返回反转的字符串

class TestChatAgentL0:
    """测试 ChatBase 的 L0 层级功能"""
    
    @pytest.fixture
    async def agent(self, db):
        """创建测试用的聊天代理"""
        chat = MockChatAgent(user_id="test_user", db=db)
        yield chat
        await chat.stop()
    
    def test_init_with_L0(self, agent):
        """测试初始化 L0 层级"""
        assert agent.thread is not None
        assert agent.user_id == "test_user"
        
    def test_thread_operations(self, agent):
        """测试线程操作"""
        # 记录原始线程ID
        original_thread_id = agent.thread_id
        
        # 创建新线程
        agent.new_thread()
        assert agent.thread_id != original_thread_id
        
        # 加载原始线程
        agent.load_thread(original_thread_id)
        assert agent.thread_id == original_thread_id
        
        # 测试无效线程ID
        with pytest.raises(ValueError):
            agent.load_thread("invalid_thread_id")
            
    def test_history_operations(self, agent):
        """测试历史记录操作"""
        # 初始状态
        agent.new_thread()
        assert len(agent.history) == 0
        assert len(agent.all_QAs) == 0
        
        # 添加一些对话
        qa = QA(
            qa_id=agent.create_request_id(),
            user_id=agent.user_id,
            thread_id=agent.thread_id,
            messages=[
                Message(role="user", content="你好"),
                Message(role="assistant", content="你好！")
            ]
        )
        agent.l0_qa.add_QA(qa)
        
        # 验证历史记录
        assert len(agent.all_QAs) == 1
        assert len(agent.history) > 0
        
    @pytest.mark.asyncio
    async def test_message_handling(self, agent):
        """测试消息处理"""
        # 测试字符串输入
        await agent._async_handler(
            messages=[
                {"role": "user", "content": "测试消息"},
            ],
            publisher=None,
            request_id="test_req_1",
        )
        
        # 测试消息列表输入
        await agent._async_handler(
            messages=[
                {"role": "system", "content": "你是一个助手"},
                {"role": "user", "content": "你好"}
            ],
            publisher=None,
            request_id="test_req_2",
        )
        
        # 验证消息是否被正确保存
        qas = agent.all_QAs
        assert len(qas) == 2
        
        # 验证系统消息是否被正确处理
        last_qa = qas[-1]
        assert last_qa.messages[0].role == "system"
        
    def test_message_normalization(self, agent):
        """测试消息规范化"""
        # 测试字符串输入
        msgs = agent.normalize_messages("测试")
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "测试"
        
        # 测试元组列表输入
        msgs = agent.normalize_messages([
            ("user", "问题"),
            ("ai", "回答")
        ])
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        
        # 测试字典列表输入
        msgs = agent.normalize_messages([
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "用户输入"}
        ])
        assert len(msgs) == 2
        assert msgs[0].role == "system"
        
    @pytest.mark.asyncio
    async def test_context_preservation(self, agent):
        """测试上下文保持"""
        # 第一轮对话
        await agent._async_handler(
            messages=[
                {"role": "user", "content": "第一条消息"},
            ],
            publisher=None,
            request_id="test_req_1",
        )
        
        # 第二轮对话
        await agent._async_handler(
            messages=[
                {"role": "user", "content": "第二条消息"},
            ],
            publisher=None,
            request_id="test_req_2",
        )
        
        # 验证历史记录中包含两轮对话
        history = agent.history
        assert len(history) >= 2
        
        # 验证新线程后历史记录清空
        agent.new_thread()
        assert len(agent.history) == 0
        
    def test_thread_listing(self, agent):
        """测试线程列表"""
        # 创建多个线程
        original_thread = agent.thread
        threads = [original_thread]
        
        for i in range(2):
            agent.new_thread()
            threads.append(agent.thread)
            
        # 验证所有线程都可以被列出
        all_threads = agent.all_threads
        assert len(all_threads) >= len(threads)
        
        # 验证每个创建的线程都能被找到
        thread_ids = [t.thread_id for t in all_threads]
        for thread in threads:
            assert thread.thread_id in thread_ids 
