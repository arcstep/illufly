import pytest
import asyncio
import logging
from unittest.mock import MagicMock
from illufly.agent.memory.base_task import BaseTask
from illufly.rocksdb import IndexedRocksDB
from typing import Any

class MockTask(BaseTask):
    """用于测试的任务类"""
    process_count = 0
    has_task = True
    
    @classmethod
    async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
        if not cls.has_task:
            return None
        return "mock_task"  # 返回一个简单的任务标识
        
    @classmethod
    async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
        # 模拟任务状态更新
        pass

    @classmethod
    async def process_todo_task(
        cls,
        db: IndexedRocksDB,
        task: Any,
        sleep_time: float = 0.1,
        raise_error: bool = False,
        **kwargs
    ) -> None:
        # 模拟任务处理
        cls.process_count += 1
        if raise_error:
            raise ValueError("测试错误")
        await asyncio.sleep(sleep_time)

class TestBaseTask:
    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=IndexedRocksDB)
    
    @pytest.fixture
    def reset_mock_task(self):
        """重置MockTask的状态"""
        MockTask.process_count = 0
        MockTask.has_task = True
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
            assert any("任务处理失败" in record.message for record in caplog.records)
            
            await MockTask.stop()
    
    async def test_multiple_stop_calls(self, mock_db, reset_mock_task):
        """测试多次调用停止"""
        MockTask.start(db=mock_db)
        await MockTask.stop()
        # 第二次停止应该安全返回
        await MockTask.stop()
        assert MockTask._instances.get(MockTask.get_task_id()) is None
    
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

    async def test_invalid_max_concurrent_tasks(self, mock_db, reset_mock_task):
        """测试无效的最大并发任务数参数"""
        with pytest.raises(ValueError, match="max_concurrent_tasks 必须是大于 0 的整数"):
            MockTask.start(db=mock_db, max_concurrent_tasks=0)
        
        with pytest.raises(ValueError, match="max_concurrent_tasks 必须是大于 0 的整数"):
            MockTask.start(db=mock_db, max_concurrent_tasks=-1)

    async def test_max_concurrent_tasks(self, mock_db, reset_mock_task):
        """测试最大并发任务限制"""
        max_tasks = 3
        MockTask.start(db=mock_db, max_concurrent_tasks=max_tasks, sleep_time=0.5)
        
        # 等待任务累积
        await asyncio.sleep(0.1)
        
        # 验证正在执行的任务数不超过最大限制
        assert len(MockTask._pending_tasks[MockTask.get_task_id()]) <= max_tasks
        
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

    async def test_parallel_execution_efficiency(self, mock_db, reset_mock_task):
        """测试不同并发配置下的任务执行效率"""
        class TimedMockTask(BaseTask):
            process_count = 0
            completed_count = 0
            _completion_event = None
            _total_tasks = 0
            
            # 覆盖基类的等待时间
            _sleep_time_when_idle = 0.01  # 减少空闲等待时间
            
            @classmethod
            async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
                if cls.process_count >= cls._total_tasks:
                    return None
                cls.process_count += 1
                return f"task_{cls.process_count}"
            
            @classmethod
            async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
                pass
            
            @classmethod
            async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
                cls.completed_count += 1
                if cls.completed_count >= cls._total_tasks:
                    cls._completion_event.set()
                await asyncio.sleep(0.05)  # 减少任务执行时间为0.05秒

        async def run_batch_tasks(max_concurrent, expected_time, task_count=10):
            # 重置计数和事件
            TimedMockTask.process_count = 0
            TimedMockTask.completed_count = 0
            TimedMockTask._completion_event = asyncio.Event()
            TimedMockTask._total_tasks = task_count
            
            # 记录开始时间
            start_time = asyncio.get_event_loop().time()
            
            # 启动任务处理器
            TimedMockTask.start(
                db=mock_db,
                max_concurrent_tasks=max_concurrent
            )
            
            # 等待所有任务完成
            await TimedMockTask._completion_event.wait()
            
            # 停止任务处理器
            await TimedMockTask.stop()
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # 允许0.1秒的误差（增加误差容忍度）
            assert abs(execution_time - expected_time) < 0.1, \
                f"预期执行时间 {expected_time}秒, 实际用时 {execution_time:.2f}秒"
            
            # 验证任务确实完成了预期数量
            assert TimedMockTask.completed_count == task_count
        
        # 测试不同并发配置（调整预期时间）
        # 2个并发，10个任务，预期0.25秒完成（10/2 * 0.05）
        await run_batch_tasks(max_concurrent=2, expected_time=0.25)
        
        # 5个并发，10个任务，预期0.1秒完成（10/5 * 0.05）
        await run_batch_tasks(max_concurrent=5, expected_time=0.1)
        
        # 10个并发，10个任务，预期0.05秒完成（10/10 * 0.05）
        await run_batch_tasks(max_concurrent=10, expected_time=0.05)

    async def test_idle_cpu_usage(self, mock_db, reset_mock_task):
        """测试空闲时的CPU使用情况"""
        class IdleTask(BaseTask):
            process_count = 0
            
            @classmethod
            async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
                cls.process_count += 1
                return None  # 始终返回无任务
            
            @classmethod
            async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
                pass
            
            @classmethod
            async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
                pass
        
        # 启动任务处理器
        IdleTask.start(db=mock_db, max_concurrent_tasks=2)
        
        # 等待一些任务处理完成
        await asyncio.sleep(0.2)
        initial_count = IdleTask.process_count
        
        # 等待一段时间
        await asyncio.sleep(0.5)
        
        # 检查在无任务期间的处理次数
        idle_attempts = IdleTask.process_count - initial_count
        attempts_per_second = idle_attempts / 0.5
        
        await IdleTask.stop()
        
        # 验证空闲时的处理频率不会太高
        assert attempts_per_second <= 20, \
            f"空闲时任务尝试频率过高: {attempts_per_second:.1f}/秒"

    async def test_idle_to_busy_transition(self, mock_db, reset_mock_task):
        """测试从空闲到繁忙状态的转换"""
        class TransitionTask(BaseTask):
            process_count = 0
            has_task = False
            task_processed = asyncio.Event()
            
            @classmethod
            async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
                if not cls.has_task:
                    return None
                return "test_task"
            
            @classmethod
            async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
                pass
            
            @classmethod
            async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
                cls.process_count += 1
                cls.task_processed.set()
            
                await asyncio.sleep(0.1)  # 模拟任务处理时间

        # 启动任务处理器
        TransitionTask.start(db=mock_db, max_concurrent_tasks=2)

        # 等待系统进入空闲状态
        await asyncio.sleep(0.2)
        
        # 记录初始计数
        initial_count = TransitionTask.process_count

        # 切换到有任务状态
        TransitionTask.has_task = True

        try:
            # 等待任务被处理
            await asyncio.wait_for(TransitionTask.task_processed.wait(), timeout=1.0)
            
            # 验证任务确实被处理了
            assert TransitionTask.process_count > initial_count, \
                "任务应该被处理"
            
        finally:
            # 清理
            await TransitionTask.stop()

    async def test_concurrent_task_processing(self, mock_db, reset_mock_task):
        """测试并发任务处理"""
        class ConcurrentTask(BaseTask):
            tasks_in_processing = set()
            max_concurrent_seen = 0
            processed_tasks = []
            
            @classmethod
            async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
                if len(cls.processed_tasks) >= 10:  # 总共处理10个任务
                    return None
                return f"task_{len(cls.processed_tasks)}"
            
            @classmethod
            async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
                cls.tasks_in_processing.add(task)
                cls.max_concurrent_seen = max(cls.max_concurrent_seen, 
                                           len(cls.tasks_in_processing))
                await asyncio.sleep(0.1)  # 模拟状态更新耗时
            
            @classmethod
            async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
                cls.tasks_in_processing.remove(task)
                cls.processed_tasks.append(task)
            
                await asyncio.sleep(0.2)  # 模拟任务处理耗时
        
        # 启动任务处理器
        ConcurrentTask.start(db=mock_db, max_concurrent_tasks=3)
        
        # 等待所有任务处理完成
        while len(ConcurrentTask.processed_tasks) < 10:
            await asyncio.sleep(0.1)
        
        await ConcurrentTask.stop()
        
        # 验证并发控制
        assert ConcurrentTask.max_concurrent_seen <= 3, \
            f"最大并发数超过限制: {ConcurrentTask.max_concurrent_seen}"
        
        # 验证任务处理顺序
        assert len(ConcurrentTask.processed_tasks) == 10, \
            f"处理的任务数量不正确: {len(ConcurrentTask.processed_tasks)}"
        assert ConcurrentTask.processed_tasks == [f"task_{i}" for i in range(10)], \
            "任务处理顺序不正确"

    async def test_task_error_handling(self, mock_db, reset_mock_task):
        """测试任务错误处理"""
        class ErrorTask(BaseTask):
            error_count = 0
            success_count = 0
            
            @classmethod
            async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs):
                if cls.error_count + cls.success_count >= 5:
                    return None
                return f"task_{cls.error_count + cls.success_count}"
            
            @classmethod
            async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
                pass
            
            @classmethod
            async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
                cls.success_count += 1

                if task == "task_1" or task == "task_3":
                    cls.error_count += 1
                    raise Exception(f"模拟任务处理错误: {task}")
                await asyncio.sleep(0.1)
        
        # 启动任务处理器
        ErrorTask.start(db=mock_db, max_concurrent_tasks=1)
        
        # 等待所有任务处理完成
        while ErrorTask.error_count + ErrorTask.success_count < 5:
            await asyncio.sleep(0.1)
        
        await ErrorTask.stop()
        
        # 验证错误处理
        assert ErrorTask.error_count == 2, \
            f"错误任务数量不正确: {ErrorTask.error_count}"
        assert ErrorTask.success_count == 3, \
            f"成功任务数量不正确: {ErrorTask.success_count}"

    async def test_start_stop(self, mock_db, reset_mock_task):
        """测试任务的启动和停止"""
        # 启动任务
        MockTask.start(db=mock_db)
        assert len(MockTask._instances) == 1
        
        # 再次启动相同的任务
        with pytest.raises(RuntimeError, match="已经在运行"):
            MockTask.start(db=mock_db)
        assert len(MockTask._instances) == 1
        assert MockTask._instances.get('MockTask') is not None
        
        # 停止任务
        await MockTask.stop()
        assert MockTask._instances.get('MockTask') is None

    async def test_task_processing(self, mock_db, reset_mock_task):
        """测试任务处理"""
        initial_count = MockTask.process_count
        
        # 启动任务处理
        MockTask.start(db=mock_db)
        await asyncio.sleep(0.3)  # 给一些时间处理任务
        
        # 验证任务被处理
        assert MockTask.process_count > initial_count
        
        await MockTask.stop()

    async def test_no_task_available(self, mock_db, reset_mock_task):
        """测试无任务可处理的情况"""
        MockTask.has_task = False
        initial_count = MockTask.process_count
        
        # 启动任务处理
        MockTask.start(db=mock_db)
        await asyncio.sleep(0.3)
        
        # 验证没有任务被处理
        assert MockTask.process_count == initial_count
        
        await MockTask.stop() 