import pytest
from datetime import datetime, timedelta

from illufly.llm.memory.L0_qa.models import QA, Message
from illufly.llm.memory.L0_qa.qa_manager import QAManager
from illufly.llm.memory.L0_qa.models import TaskState

class TestQA:
    """问答测试"""
    
    @pytest.fixture
    def sample_qa(self, user_id):
        """创建示例问答"""
        return QA(
            qa_id="test_qa_id1",
            user_id=user_id,
            thread_id="sample_thread_id",
            messages=[
                ("user", "你好"),
                ("ai", "你好！很高兴见到你。")
            ]
        )
    
    @pytest.fixture
    def qa_with_system(self, user_id):
        """创建带系统提示的问答"""
        return QA(
            qa_id="test_qa_id2",
            user_id=user_id,
            thread_id="sample_thread_id",
            messages=[
                ("system", "你是一个友好的助手"),
                ("user", "你是谁？"),
                ("assistant", "我是一个友好的AI助手。")
            ]
        )

    def test_qa_creation(self, sample_qa, user_id, db):
        """测试问答创建"""
        # 验证基本属性
        thread_id = "sample_thread_id"
        sample_qa.thread_id = thread_id

        assert sample_qa.qa_id == "test_qa_id1"
        assert len(sample_qa.messages) == 2
        assert sample_qa.used_time >= 0
        
        # 验证消息转换
        assert all(isinstance(m, Message) for m in sample_qa.messages)
        assert sample_qa.messages[1].role == "assistant"  # 验证 ai -> assistant 转换
        
        # 验证存储
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=sample_qa.thread_id)
        manager.set_qa(sample_qa)
        
        # 验证检索
        stored_qa = manager.get_qa(sample_qa.thread_id, sample_qa.qa_id)
        assert stored_qa is not None

        # 验证所有QA
        all_qas = manager.get_all(sample_qa.thread_id)
        assert len(all_qas) == 1
        assert all_qas[0].qa_id == sample_qa.qa_id

    def test_qa_properties(self, sample_qa):
        """测试问答属性"""
        # 测试问题提取
        assert sample_qa.question == "你好"
        
        # 测试答案提取
        assert sample_qa.answer == "你好！很高兴见到你。"
        

    def test_retrieve_with_system_message(self, user_id, db, qa_with_system):
        """测试带系统消息的检索"""
        thread_id = "test_thread_id_system_message"
        qa_with_system.thread_id = thread_id

        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=qa_with_system.thread_id)
        manager.set_qa(qa_with_system)
        
        # 检索时带入新的系统消息
        new_system_msg = Message(role="system", content="新的系统提示")
        messages = manager.retrieve(
            thread_id=qa_with_system.thread_id,
            messages=[new_system_msg]
        )
        
        # 验证系统消息被正确处理
        assert messages[0].role == "system"
        assert messages[0].content == "新的系统提示"

    def test_retrieve_once_thread(self, user_id, db):
        """测试once线程的检索行为"""
        manager = QAManager(db, user_id=user_id)
        
        # 创建一些测试消息
        test_messages = [
            Message(role="user", content="测试消息")
        ]
        
        # 检索 once 线程
        messages = manager.retrieve(thread_id="once", messages=test_messages)
        
        # 验证消息直接返回，不包含历史
        assert len(messages) == len(test_messages)
        assert messages == test_messages

    def test_retrieve_with_summary(self, user_id, db):
        """测试带摘要的问答检索"""
        thread_id = "test_thread_id_summary"
        qa = QA(
            qa_id="test_qa_summary",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="请详细解释Python的特点"),
                Message(role="assistant", content="Python是一种高级编程语言，具有以下特点：\n1. 简洁的语法\n2. 丰富的库\n3. 跨平台支持\n...")
            ],
            summary=[
                Message(role="user", content="Python特点"),
                Message(role="assistant", content="简要说明了Python的主要特点")
            ]
        )
        
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        manager.set_qa(qa)
        
        # 检索并验证使用摘要
        messages = manager.retrieve(thread_id=thread_id)
        assert len(messages) == 2
        assert messages[1].content == "简要说明了Python的主要特点"

    def test_retrieve_multiple_qas(self, user_id, db):
        """测试多轮问答检索"""
        thread_id = "test_thread_id_multiple_qas"
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        # 创建多个问答
        for i in range(12):  # 创建超过默认限制的问答
            qa = QA(
                qa_id=f"test_qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ]
            )
            manager.set_qa(qa)
        
        # 使用默认限制检索
        messages = manager.retrieve(thread_id)
        assert len(messages) <= 20  # 验证默认限制
        
        # 使用自定义限制检索
        messages = manager.retrieve(thread_id, limit=5)
        assert len(messages) <= 10  # 考虑到每个QA有两条消息

    def test_task_flags_initial_state(self, sample_qa):
        """测试任务标记的初始状态"""
        assert sample_qa.task_summarize == TaskState.TODO
        assert sample_qa.task_extract_facts == TaskState.TODO

    def test_summarise_todo_list(self, user_id, db):
        """测试摘要待办任务列表"""
        thread_id = "test_thread_todo"
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        # 创建多个QA，部分需要摘要
        qas = [
            QA(
                qa_id=f"qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ],
                task_summarize=TaskState.TODO if i % 2 == 0 else TaskState.DONE
            )
            for i in range(4)
        ]
        
        for qa in qas:
            manager.set_qa(qa)
        
        # 获取待办任务列表
        todo_list = manager.summarise_todo_list()
        assert len(todo_list) == 2  # 应该有2个待办任务
        assert all(qa.task_summarize == TaskState.TODO for qa in todo_list)

    def test_extract_facts_todo_list(self, user_id, db):
        """测试事实提取待办任务列表"""
        thread_id = "test_thread_facts"
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        # 创建多个QA，部分需要提取事实
        qas = [
            QA(
                qa_id=f"qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ],
                task_extract_facts=TaskState.TODO if i % 3 == 0 else TaskState.DONE
            )
            for i in range(6)
        ]
        
        for qa in qas:
            manager.set_qa(qa)
        
        # 获取待办任务列表
        todo_list = manager.extract_facts_todo_list()
        assert len(todo_list) == 2  # 应该有2个待办任务
        assert all(qa.task_extract_facts == TaskState.TODO for qa in todo_list)

    def test_task_state_updates(self, user_id, db):
        """测试任务状态更新"""
        thread_id = "test_thread_updates"
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        # 创建一个需要处理的QA
        qa = QA(
            qa_id="test_qa",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="测试问题"),
                Message(role="assistant", content="测试回答")
            ]
        )
        qa.task_summarize = TaskState.DONE
        manager.set_qa(qa)

        # 验证待办列表
        assert len(manager.summarise_todo_list()) == 0
        assert len(manager.extract_facts_todo_list()) == 1
        
        # 更新摘要状态
        updated_qa = QA(**manager.get_qa(thread_id, qa.qa_id))
        assert updated_qa.task_summarize == TaskState.DONE
        assert updated_qa.task_extract_facts == TaskState.TODO  # 不应影响其他标记
        
        # 更新事实提取状态
        qa.task_extract_facts = TaskState.DONE
        manager.set_qa(qa)
        updated_qa = QA(**manager.get_qa(thread_id, qa.qa_id))
        assert updated_qa.task_extract_facts == TaskState.DONE
        
        # 验证待办列表更新
        assert len(manager.summarise_todo_list()) == 0
        assert len(manager.extract_facts_todo_list()) == 0

    def test_task_state_error_handling(self, user_id, db):
        """测试任务状态错误处理"""
        thread_id = "test_thread_errors"
        manager = QAManager(db, user_id=user_id)
        manager.create_thread(thread_id=thread_id)
        
        qa = QA(
            qa_id="test_qa",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="测试问题"),
                Message(role="assistant", content="测试回答")
            ]
        )
        qa.task_summarize = TaskState.ERROR
        manager.set_qa(qa)
        
        # 测试设置错误状态
        updated_qa = QA(**manager.get_qa(thread_id, qa.qa_id))
        assert updated_qa.task_summarize == TaskState.ERROR
        
        # 测试从错误状态恢复
        qa.task_summarize = TaskState.TODO
        manager.set_qa(qa)
        updated_qa = QA(**manager.get_qa(thread_id, qa.qa_id))
        assert updated_qa.task_summarize == TaskState.TODO
