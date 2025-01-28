import pytest
from datetime import datetime
from typing import List, Dict, Any

from illufly.llm.chat_base import ChatBase
from illufly.llm.memory.L0_QA.models import Message, QA, Thread
from illufly.mq import Publisher, StreamingBlock, BlockType, TextChunk

class MockChatAgent(ChatBase):
    """模拟的聊天代理"""
    async def _async_generate_from_llm(
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
        chat = MockChatAgent(user_id="test_user", db=db, levels={"L0"})
        yield chat
        await chat.stop()
    
    @pytest.fixture
    async def agent_without_L0(self, db):
        """创建不包含 L0 层级的聊天代理"""
        chat = MockChatAgent(user_id="test_user", db=db, levels={"L1", "L2"})
        yield chat
        await chat.stop()

    def test_init_with_L0(self, agent):
        """测试初始化 L0 层级"""
        assert "L0" in agent._levels
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
        assert len(agent.history) == 0
        assert len(agent.all_QAs) == 0
        
        # 添加一些对话
        qa = QA(
            user_id=agent.user_id,
            thread_id=agent.thread_id,
            messages=[
                Message(role="user", content="你好"),
                Message(role="assistant", content="你好！")
            ]
        )
        agent._l0_qa.add_QA(qa)
        
        # 验证历史记录
        assert len(agent.all_QAs) == 1
        assert len(agent.history) > 0
        
    @pytest.mark.asyncio
    async def test_message_handling(self, agent):
        """测试消息处理"""
        # 测试字符串输入
        await agent._async_handler(
            messages="测试消息",
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
            messages="第一条消息",
            publisher=None,
            request_id="test_req_1",
        )
        
        # 第二轮对话
        await agent._async_handler(
            messages="第二条消息",
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

    def test_init_without_L0(self, agent_without_L0):
        """测试初始化时不包含 L0 层级"""
        assert "L0" not in agent_without_L0._levels
        assert agent_without_L0.thread is None
        assert agent_without_L0.thread_id is None
        
    def test_L0_operations_when_disabled(self, agent_without_L0):
        """测试禁用 L0 时的操作行为"""
        # 验证所有 L0 相关属性都返回空值
        assert len(agent_without_L0.all_threads) == 0
        assert len(agent_without_L0.history) == 0
        assert len(agent_without_L0.history_messages) == 0
        assert len(agent_without_L0.all_QAs) == 0
        
        # 验证线程操作无效
        agent_without_L0.new_thread()  # 不应该创建新线程
        assert agent_without_L0.thread is None
        
        # 验证加载线程无效
        agent_without_L0.load_thread("some_thread_id")  # 不应该加载线程
        assert agent_without_L0.thread is None
        
    @pytest.mark.asyncio
    async def test_message_handling_without_L0(self, agent_without_L0):
        """测试禁用 L0 时的消息处理"""
        # 发送消息应该仍然工作，但不会保存历史
        await agent_without_L0._async_handler(
            messages="测试消息",
            publisher=None,
            request_id="test_req_1",
        )
        
        # 验证没有保存历史记录
        assert len(agent_without_L0.all_QAs) == 0
        assert len(agent_without_L0.history) == 0
        
        # 测试复杂消息输入
        await agent_without_L0._async_handler(
            messages=[
                {"role": "system", "content": "你是一个助手"},
                {"role": "user", "content": "你好"}
            ],
            publisher=None,
            request_id="test_req_2",
        )
        
        # 验证仍然没有历史记录
        assert len(agent_without_L0.all_QAs) == 0
        
    def test_mixed_levels_initialization(self, db):
        """测试混合层级初始化"""
        # 测试不同层级组合
        agent_L1_only = MockChatAgent(user_id="test_user", db=db, levels={"L1"})
        assert "L0" not in agent_L1_only._levels
        assert agent_L1_only.thread is None
        
        agent_L0_L2 = MockChatAgent(user_id="test_user", db=db, levels={"L0", "L2"})
        assert "L0" in agent_L0_L2._levels
        assert agent_L0_L2.thread is not None
        
        agent_all = MockChatAgent(user_id="test_user", db=db, levels={"L0", "L1", "L2", "L3"})
        assert "L0" in agent_all._levels
        assert agent_all.thread is not None 