import pytest
import asyncio
import logging
from unittest.mock import MagicMock
from illufly.llm.tasks.base_task import BaseTask
from illufly.io.rocksdict import IndexedRocksDB

class MockTask(BaseTask):
    """用于测试的模拟任务类"""
    process_count = 0
    
    @classmethod
    async def _process_batch(cls, db: IndexedRocksDB, **kwargs):
        cls.process_count += 1
        if kwargs.get('raise_error'):
            raise ValueError("测试错误")
        await asyncio.sleep(0.1)  # 模拟处理时间

class TestBaseTask:
    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=IndexedRocksDB)
    
    @pytest.fixture
    def reset_mock_task(self):
        """重置MockTask的状态"""
        MockTask.process_count = 0
        # 清理类变量
        for task_id in list(MockTask._instances.keys()):
            MockTask._instances.pop(task_id, None)
            MockTask._stop_events.pop(task_id, None)
            MockTask._server_tasks.pop(task_id, None)
            MockTask._loggers.pop(task_id, None)
        yield
    
    def test_direct_instantiation(self):
        """测试直接实例化应该失败"""
        with pytest.raises(RuntimeError, match="请使用.*start().*启动任务"):
            MockTask()
    
    async def test_task_lifecycle(self, mock_db, reset_mock_task):
        """测试任务生命周期"""
        # 启动任务
        MockTask.start(db=mock_db, sleep_time=0.1)
        assert MockTask._instances.get(MockTask.get_task_id()) is not None
        
        # 等待几个处理周期
        await asyncio.sleep(0.3)
        assert MockTask.process_count > 0
        
        # 停止任务
        await MockTask.stop()
        assert MockTask._instances.get(MockTask.get_task_id()) is None
        assert MockTask._server_tasks.get(MockTask.get_task_id()) is None
    
    async def test_duplicate_start(self, mock_db, reset_mock_task):
        """测试重复启动任务"""
        MockTask.start(db=mock_db)
        with pytest.raises(RuntimeError, match="已经在运行"):
            MockTask.start(db=mock_db)
        await MockTask.stop()
    
    async def test_error_handling(self, mock_db, reset_mock_task, caplog):
        """测试错误处理"""
        with caplog.at_level(logging.ERROR):
            MockTask.start(db=mock_db, raise_error=True, sleep_time=0.1)
            await asyncio.sleep(0.3)
            
            # 验证错误被记录
            assert any("任务循环发生错误" in record.message for record in caplog.records)
            
            await MockTask.stop()
    
    async def test_multiple_stop_calls(self, mock_db, reset_mock_task):
        """测试多次调用停止"""
        MockTask.start(db=mock_db)
        await MockTask.stop()
        # 第二次停止应该安全返回
        await MockTask.stop()
        assert MockTask._instances.get(MockTask.get_task_id()) is None
    
    async def test_custom_logger(self, mock_db, reset_mock_task):
        """测试自定义日志记录器"""
        custom_logger = logging.getLogger("custom")
        MockTask.start(db=mock_db, logger=custom_logger)
        assert MockTask._loggers[MockTask.get_task_id()] == custom_logger
        await MockTask.stop() 