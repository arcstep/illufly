import pytest
import asyncio
import logging
from unittest.mock import MagicMock
from illufly.llm.tasks.base_task import BaseTask
from illufly.io.rocksdict import IndexedRocksDB

class MockTask(BaseTask):
    """用于测试的模拟任务类"""
    process_count = 0
    last_result = None
    
    @classmethod
    async def _process_task(cls, db: IndexedRocksDB, **kwargs):
        cls.process_count += 1
        if kwargs.get('raise_error'):
            raise ValueError("测试错误")
        if kwargs.get('sleep_time'):
            await asyncio.sleep(kwargs['sleep_time'])
        cls.last_result = kwargs.get('result', None)
        return cls.last_result

class TestBaseTask:
    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=IndexedRocksDB)
    
    @pytest.fixture
    def reset_mock_task(self):
        """重置MockTask的状态"""
        MockTask.process_count = 0
        MockTask.last_result = None
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
            MockTask.start(db=mock_db, raise_error=True)
            await asyncio.sleep(0.3)
            
            # 验证错误被记录
            assert any("任务执行错误" in record.message for record in caplog.records)
            
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

    async def test_max_concurrent_tasks(self, mock_db, reset_mock_task):
        """测试最大并发任务限制"""
        max_tasks = 3
        MockTask.start(db=mock_db, max_concurrent_tasks=max_tasks, sleep_time=0.5)
        
        # 等待任务累积
        await asyncio.sleep(0.1)
        
        # 验证正在执行的任务数不超过最大限制
        assert len(MockTask._pending_tasks[MockTask.get_task_id()]) <= max_tasks
        
        await MockTask.stop()

    async def test_invalid_max_concurrent_tasks(self, mock_db, reset_mock_task):
        """测试无效的最大并发任务数参数"""
        with pytest.raises(ValueError, match="max_concurrent_tasks 必须是大于 0 的整数"):
            MockTask.start(db=mock_db, max_concurrent_tasks=0)
        
        with pytest.raises(ValueError, match="max_concurrent_tasks 必须是大于 0 的整数"):
            MockTask.start(db=mock_db, max_concurrent_tasks=-1)

    async def test_task_result_handling(self, mock_db, reset_mock_task):
        """测试任务执行结果"""
        expected_result = {"status": "success"}
        MockTask.start(db=mock_db, result=expected_result)
        
        # 等待任务执行
        await asyncio.sleep(0.2)
        
        assert MockTask.last_result == expected_result
        await MockTask.stop()

    async def test_concurrent_execution(self, mock_db, reset_mock_task):
        """测试并发执行情况"""
        max_tasks = 3
        MockTask.start(
            db=mock_db,
            max_concurrent_tasks=max_tasks,
            sleep_time=0.3  # 每个任务执行时间
        )
        
        # 等待任务累积和执行
        await asyncio.sleep(0.5)
        
        # 验证有任务在并发执行
        pending_tasks = len(MockTask._pending_tasks[MockTask.get_task_id()])
        assert 0 < pending_tasks <= max_tasks
        
        await MockTask.stop()

    async def test_task_cleanup(self, mock_db, reset_mock_task):
        """测试任务清理"""
        MockTask.start(db=mock_db)
        await asyncio.sleep(0.1)
        
        # 正常停止时
        await MockTask.stop()
        assert not MockTask._pending_tasks.get(MockTask.get_task_id())
        
        # 重新启动并强制停止
        MockTask.start(db=mock_db)
        await asyncio.sleep(0.1)
        await MockTask.stop()
        
        # 验证资源被正确清理
        assert not MockTask._instances.get(MockTask.get_task_id())
        assert not MockTask._server_tasks.get(MockTask.get_task_id())
        assert not MockTask._pending_tasks.get(MockTask.get_task_id())

    async def test_parallel_execution_efficiency(self, mock_db, reset_mock_task):
        """测试不同并发配置下的任务执行效率"""
        class TimedMockTask(BaseTask):
            completed_count = 0
            _completion_event = None
            
            @classmethod
            async def _process_task(cls, db: IndexedRocksDB, **kwargs):
                await asyncio.sleep(0.1)  # 固定任务执行时间
                cls.completed_count += 1
                if cls.completed_count >= kwargs.get('task_count', 10):
                    cls._completion_event.set()
                return True
        
        async def run_batch_tasks(max_concurrent, expected_time, task_count=10):
            # 重置计数和事件
            TimedMockTask.completed_count = 0
            TimedMockTask._completion_event = asyncio.Event()
            
            # 记录开始时间
            start_time = asyncio.get_event_loop().time()
            
            # 启动任务处理器
            TimedMockTask.start(
                db=mock_db,
                max_concurrent_tasks=max_concurrent,
                task_count=task_count
            )
            
            # 等待所有任务完成
            await TimedMockTask._completion_event.wait()
            
            # 停止任务处理器
            await TimedMockTask.stop()
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # 允许0.05秒的误差（减小误差范围）
            assert abs(execution_time - expected_time) < 0.05, \
                f"预期执行时间 {expected_time}秒, 实际用时 {execution_time:.2f}秒"
            
            # 验证任务确实完成了预期数量
            assert TimedMockTask.completed_count == task_count
        
        # 测试不同并发配置
        # 2个并发，10个任务，预期0.5秒完成（10/2 * 0.1）
        await run_batch_tasks(max_concurrent=2, expected_time=0.5)
        
        # 5个并发，10个任务，预期0.2秒完成（10/5 * 0.1）
        await run_batch_tasks(max_concurrent=5, expected_time=0.2)
        
        # 10个并发，10个任务，预期0.1秒完成（10/10 * 0.1）
        await run_batch_tasks(max_concurrent=10, expected_time=0.1) 