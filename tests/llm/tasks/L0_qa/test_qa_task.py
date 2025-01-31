import pytest
import asyncio
import logging
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from illufly.llm.tasks.L0_qa.qa_task import QaTask
from illufly.llm.memory.L0_qa import QA, Message
from illufly.llm.memory.types import TaskState, MemoryType
from illufly.mq import TextChunk, BlockType, StreamingBlock

class TestQaTask:
    @pytest.fixture
    def setup_qa(self, db, user_id, thread_id):
        """准备测试用的QA数据"""
        qa = QA(
            qa_id="test_qa",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="测试问题"),
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
            mock_instance = mock_class.return_value
            
            # 使用 AsyncMock 来模拟异步方法
            async_call_mock = AsyncMock()
            async def mock_async_call(*args, **kwargs):
                from illufly.mq import StreamingBlock, BlockType
                yield StreamingBlock(
                    block_type=BlockType.TEXT_CHUNK,
                    request_id="test_qa",
                    text="测试摘要"
                )
            
            # 设置 async_call 的 side_effect
            async_call_mock.side_effect = mock_async_call
            mock_instance.async_call = async_call_mock
            
            yield mock_instance
    
    async def test_qa_processing(self, db, setup_qa, reset_qa_task, mock_chat_openai):
        """测试QA处理"""
        # 验证初始状态
        target_qa = QA.model_validate(
            db[setup_qa.key]
        )
        assert target_qa.task_summarize == TaskState.TODO
        
        # 确认任务列表
        tasks = QaTask.get_tasks(db, 1)
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
    
    async def test_empty_todo_list(self, db, reset_qa_task, mock_chat_openai):
        """测试空的待处理列表"""
        QaTask.start(db=db, sleep_time=0.1, assistant=mock_chat_openai)
        await asyncio.sleep(0.3)
        
        # 验证没有调用处理方法
        mock_chat_openai.async_call.assert_not_called()
        
        await QaTask.stop()
    
    async def test_processing_error(self, db, setup_qa, reset_qa_task, mock_chat_openai, caplog):
        """测试处理错误"""
        mock_chat_openai.async_call.side_effect = Exception("测试错误")
        
        with caplog.at_level(logging.ERROR):
            QaTask.start(db=db, sleep_time=0.1)
            await asyncio.sleep(0.3)
            
            # 验证错误处理
            assert any("处理QA" in record.message for record in caplog.records)
            
            # 验证错误状态
            updated_qa = QA.model_validate(
                db[setup_qa.key]
            )
            assert updated_qa.task_summarize == TaskState.ERROR
            
            await QaTask.stop()
    
    async def test_batch_processing(self, db, user_id, thread_id, reset_qa_task, mock_chat_openai):
        """测试批量处理"""
        # 创建多个测试QA
        test_qas = []
        for i in range(3):
            qa = QA(
                qa_id=f"test_qa_{i}",
                user_id=user_id,
                thread_id=thread_id,
                messages=[
                    Message(role="user", content=f"问题{i}"),
                    Message(role="assistant", content=f"回答{i}")
                ],
                task_summarize=TaskState.TODO
            )
            db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
            test_qas.append(qa)
        
        QaTask.start(db=db, sleep_time=0.1, batch_size=2)
        await asyncio.sleep(0.5)  # 给足够时间处理所有QA
        
        # 验证所有QA都被处理
        for qa in test_qas:
            updated_qa = QA.model_validate(
                db[qa.key]
            )
            assert updated_qa.task_summarize == TaskState.DONE
            assert updated_qa.summary == "测试摘要"
        
        await QaTask.stop()
    
    async def test_summary_processing(self, db, user_id, thread_id, reset_qa_task, mock_chat_openai):
        """测试摘要处理逻辑"""
        qa = QA(
            qa_id="test_qa_long",
            user_id=user_id,
            thread_id=thread_id,
            messages=[
                Message(role="user", content="这是一个很长的问题" * 10),
                Message(role="assistant", content="这是一个很长的回答" * 10)
            ],
            task_summarize=TaskState.TODO
        )
        db.update_with_indexes(MemoryType.QA, qa.key, qa.model_dump())
        
        QaTask.start(db=db, sleep_time=0.1)
        await asyncio.sleep(0.3)
        
        # 验证长文本被处理
        updated_qa = QA.model_validate(
            db[qa.key]
        )
        assert updated_qa.task_summarize == TaskState.DONE
        assert updated_qa.summary == "测试摘要"
        
        await QaTask.stop() 