import pytest
import asyncio
import logging
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from illufly.llm.tasks.L0_qa.qa_task import QaTask
from illufly.llm.memory.L0_qa import QA, Message
from illufly.llm.memory.types import TaskState, MemoryType
from illufly.mq import TextChunk, BlockType

class TestQaTask:
    @pytest.fixture
    def setup_qa(self, db, user_id, thread_id):
        """准备测试用的QA数据"""
        qa = QA(
            qa_id="test_qa",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="测试问题"*100),
                Message(role="assistant", content="测试摘要")
            ],
            task_summarize=TaskState.TODO
        )
        # 直接写入数据库
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
        return qa
    
    @pytest.fixture
    def reset_qa_task(self):
        """重置QaTask的状态"""
        for task_id in list(QaTask._instances.keys()):
            QaTask._instances.pop(task_id, None)
            QaTask._stop_events.pop(task_id, None)
            QaTask._server_tasks.pop(task_id, None)
            QaTask._loggers.pop(task_id, None)
        yield
    
    @pytest.fixture
    def mock_chat_openai(self):
        with patch('illufly.llm.chat_openai.ChatOpenAI') as mock_class:
            async def mock_async_call(*args, **kwargs):
                """模拟异步生成器"""
                await asyncio.sleep(0.1)
                yield TextChunk(request_id="test_qa", text="测试摘要")
            mock_class.return_value.async_call = mock_async_call            
            yield mock_class.return_value
    
    async def test_qa_processing(self, db, setup_qa, reset_qa_task, mock_chat_openai):
        """测试QA处理"""
        # 验证初始状态
        target_qa = QA.model_validate(
            db[setup_qa.key]
        )
        assert target_qa.task_summarize == TaskState.TODO
        
        # 确认任务列表
        tasks = QaTask.get_todo_tasks(db)
        assert len(tasks) == 1
        assert tasks[0].key == setup_qa.key
        
        # 启动任务，注入mock的chat实例
        QaTask.start(
            db=db,
            sleep_time=0.1,
            assistant=mock_chat_openai  # 注入mock实例
        )
        await asyncio.sleep(0.3)
        
        # 验证处理结果
        target_qa = QA.model_validate(
            db[setup_qa.key]
        )
        assert target_qa.task_summarize == TaskState.DONE
        assert target_qa.summary[1].content == "测试摘要"
        
        await QaTask.stop()
    
    async def test_batch_processing(self, db, user_id, thread_id, reset_qa_task, mock_chat_openai):
        """测试批量处理"""
        # 创建多个测试QA
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        test_qas = []
        for i in range(10):
            qa = QA(
                qa_id=f"test_qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}"*100)
                ],
                task_summarize=TaskState.TODO
            )
            db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
            test_qas.append(qa)
        
        QaTask.start(db=db, max_concurrent_tasks=10, assistant=mock_chat_openai)
        await asyncio.sleep(0.5)  # 给足够时间处理所有QA
        
        # 验证所有QA都被处理
        for qa in test_qas:
            updated_qa = QA.model_validate(
                db[qa.key]
            )
            assert updated_qa.task_summarize == TaskState.DONE
            assert updated_qa.summary[1].content == "测试摘要"
        
        await QaTask.stop()
    
    async def test_summary_processing(self, db, user_id, thread_id, reset_qa_task, mock_chat_openai):
        """测试摘要处理逻辑"""
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        qa = QA(
            qa_id="test_qa_long",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="这是一个很长的问题" * 50),
                Message(role="assistant", content="这是一个很长的回答" * 50)
            ],
            task_summarize=TaskState.TODO
        )
        db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
        QaTask.start(db=db, sleep_time=0.1, assistant=mock_chat_openai)
        await asyncio.sleep(0.3)
        
        # 验证长文本被处理
        updated_qa = QA.model_validate(
            db[qa.key]
        )
        assert updated_qa.task_summarize == TaskState.DONE
        assert updated_qa.summary[1].content == "测试摘要"
        
        await QaTask.stop()
    
    async def test_reset_processing_tasks(self, db, user_id, thread_id, reset_qa_task):
        """测试重置处理中任务的功能"""
        # 准备测试数据：创建多个不同状态的QA
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        
        test_qas = []
        states = [
            TaskState.TODO,
            TaskState.PROCESSING,
            TaskState.PROCESSING,
            TaskState.DONE,
            TaskState.ERROR
        ]
        
        for i, state in enumerate(states):
            qa = QA(
                qa_id=f"test_qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ],
                task_summarize=state
            )
            db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
            test_qas.append(qa)
        
        # 执行重置操作
        QaTask.reset_processing_task(db)
        
        # 验证结果
        for i, qa in enumerate(test_qas):
            updated_qa = QA.model_validate(db[qa.key])
            if states[i] == TaskState.PROCESSING:
                # PROCESSING 状态应该被重置为 TODO
                assert updated_qa.task_summarize == TaskState.TODO, \
                    f"QA {i} 应该被重置为 TODO 状态"
            else:
                # 其他状态应该保持不变
                assert updated_qa.task_summarize == states[i], \
                    f"QA {i} 状态不应该改变"
    
    async def test_concurrent_task_processing(self, db, user_id, thread_id, mock_chat_openai):
        """测试并发任务处理时的状态管理"""
        # 准备测试数据
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        
        # 创建多个待处理任务
        test_qas = []
        for i in range(5):
            qa = QA(
                qa_id=f"test_qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}"*100)
                ],
                task_summarize=TaskState.TODO
            )
            db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
            test_qas.append(qa)
        
        # 启动任务处理器，设置并发数
        QaTask.start(
            db=db,
            max_concurrent_tasks=2,
            assistant=mock_chat_openai
        )
        await asyncio.sleep(0.3)
        
        # 立即检查处理中的任务
        processing_tasks = QaTask.get_processing_tasks(db)
        logging.info(f"processing_tasks: {len(processing_tasks)}")
        todo_tasks = QaTask.get_todo_tasks(db)
        logging.info(f"todo_tasks: {len(todo_tasks)}")
        
        # 验证处理中的任务数量
        assert len(processing_tasks) > 0, "应该有任务处于 PROCESSING 状态"
        assert len(processing_tasks) <= 2, f"处理中的任务数量应该不超过并发数2，当前为{len(processing_tasks)}"
        
        # 等待所有任务完成
        all_done = False
        for _ in range(50):  # 最多等待1秒
            await asyncio.sleep(0.02)
            if all(
                QA.model_validate(db[qa.key]).task_summarize == TaskState.DONE
                for qa in test_qas
            ):
                all_done = True
                break
        
        assert all_done, "部分任务未能完成"
        
        await QaTask.stop()
    
    async def test_task_state_transition(self, db, user_id, thread_id, reset_qa_task, mock_chat_openai):
        """测试任务状态转换的完整性"""
        # 准备测试数据
        db.register_model(MemoryType.QA, QA)
        db.register_indexes(MemoryType.QA, QA, field_path="task_summarize")
        
        # 创建一个测试任务
        qa = QA(
            qa_id="test_qa_transition",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="测试问题"),
                Message(role="assistant", content="测试回答")
            ],
            task_summarize=TaskState.TODO
        )
        db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
        
        # 获取任务并检查状态转换
        fetched_qa = QaTask.fetch_task(db)
        assert fetched_qa is not None
        assert fetched_qa.task_summarize == TaskState.PROCESSING
        
        # 验证数据库中的状态也已更新
        updated_qa = QA.model_validate(db[qa.key])
        assert updated_qa.task_summarize == TaskState.PROCESSING 