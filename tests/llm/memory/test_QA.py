import pytest
from datetime import datetime, timedelta

from illufly.llm.memory.L0_QA.models import QA, Message
from illufly.llm.memory.L0_QA.qa_manager import QAManager

class TestQA:
    """对话测试"""
    
    @pytest.fixture
    def L0_QA(self, user_id, thread_id):
        """创建 L0 层级的对话"""
        return QA(
            user_id=user_id,
            thread_id=thread_id,
            level="L0",  # 显式设置为 L0
            messages=[
                Message(role="user", content="你好"),
                Message(role="assistant", content="你好！很高兴见到你。")
            ]
        )
    
    @pytest.fixture
    def l1_QA(self, user_id, thread_id):
        """创建 L1 层级的对话"""
        return QA(
            user_id=user_id,
            thread_id=thread_id,
            level="L1",  # 显式设置为 L1
            messages=[
                Message(role="user", content="这是什么？"),
                Message(role="assistant", content="这是一个测试对话。")
            ]
        )

    def test_QA_creation(self, L0_QA, user_id, db):
        """测试对话创建"""
        assert L0_QA.qa_id is not None

        manager = QAManager(db, user_id=user_id)
        manager.create_thread(title="测试对话", description="测试对话", thread_id=L0_QA.thread_id)
        manager.add_QA(L0_QA)

        # 验证对话是否成功添加
        all_threads = manager.all_threads()
        assert L0_QA.thread_id in [thread.thread_id for thread in all_threads]

        # 验证对话是否成功添加
        all_QAs = manager.all_QAs(L0_QA.thread_id)
        assert L0_QA.qa_id in [QA.qa_id for QA in all_QAs]

    def test_retrieve_QAs(self, user_id, thread_id, db, L0_QA, l1_QA):
        """测试对话检索功能"""
        # 创建管理器并添加对话
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        # 添加不同层级的对话
        manager.add_QA(L0_QA)
        manager.add_QA(l1_QA)
        
        # 检索对话
        messages = manager.retrieve(thread_id)
        
        # 验证检索结果
        assert len(messages) == 2  # 只应该返回 L0 层级的对话
        assert messages == [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！很高兴见到你。"}
        ]

    def test_retrieve_with_summary(self, user_id, thread_id, db):
        """测试带有摘要的对话检索"""
        # 创建带有摘要的对话
        qa = QA(
            user_id=user_id,
            thread_id=thread_id,
            level="L0",
            messages=[
                Message(role="user", content="请解释什么是Python"),
                Message(role="assistant", content="Python是一种高级编程语言，以其简洁的语法和丰富的生态系统而闻名...")
            ],
            summary=[
                Message(role="user", content="Python的定义，"),
                Message(role="assistant", content="AI根据常识提供了简要解释")
            ]
        )
        
        # 创建管理器并添加对话
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        manager.add_QA(qa)
        
        # 检索对话
        messages = manager.retrieve(thread_id)
        
        # 验证检索结果使用了摘要
        assert len(messages) == 2
        assert messages == [
            {"role": "user", "content": "Python的定义，"},
            {"role": "assistant", "content": "AI根据常识提供了简要解释"}
        ]

    def test_retrieve_multiple_QAs(self, user_id, thread_id, db):
        """测试多轮对话检索"""
        # 创建多轮对话
        QAs = [
            QA(
                user_id=user_id,
                thread_id=thread_id,
                level="L0",
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ]
            )
            for i in range(3)
        ]
        
        # 添加一个非L0对话
        QAs.append(QA(
            user_id=user_id,
            thread_id=thread_id,
            level="L1",
            messages=[
                Message(role="user", content="另一个问题"),
                Message(role="assistant", content="另一个回答")
            ]
        ))
        
        # 创建管理器并添加对话
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        for qa in QAs:
            manager.add_QA(qa)
        
        # 检索对话
        messages = manager.retrieve(thread_id)
        
        # 验证检索结果
        assert len(messages) == 6  # 只应该返回6个L0对话
