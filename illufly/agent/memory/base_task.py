from typing import List, Optional, ClassVar, Dict, Any
from abc import ABC, abstractmethod
import asyncio
import logging

from ..async_utils import AsyncUtils
from ..rocksdb import IndexedRocksDB

class BaseTask(ABC):
    """异步任务基类"""
    
    _instances: ClassVar[dict] = {}  # 存储不同任务类型的实例
    _stop_events: ClassVar[dict] = {}  # 存储不同任务的停止事件
    _server_tasks: ClassVar[dict] = {}  # 存储不同任务的服务任务
    _loggers: ClassVar[dict] = {}  # 存储不同任务的日志记录器
    _pending_tasks: ClassVar[dict] = {}  # 存储每个任务类型的待处理任务集合
    
    # 控制空转的类变量
    _sleep_time_when_idle = 0.1  # 无任务时的等待时间
    _sleep_time_on_error = 0.3   # 发生错误时的等待时间
    
    def __init__(self):
        raise RuntimeError(f"请使用 {self.__class__.__name__}.start() 启动任务")
    
    @classmethod
    def get_task_id(cls) -> str:
        """获取任务ID，默认使用类名"""
        return cls.__name__

    @classmethod
    @abstractmethod
    async def fetch_todo_task(cls, db: IndexedRocksDB, **kwargs) -> Optional[Any]:
        """获取一个待处理的任务，如果没有则返回None"""
        pass
    
    @classmethod
    @abstractmethod
    async def task_to_processing(cls, db: IndexedRocksDB, task: Any) -> None:
        """将任务状态更新为处理中"""
        pass
    
    @classmethod
    @abstractmethod
    async def process_todo_task(cls, db: IndexedRocksDB, task: Any, **kwargs) -> None:
        """处理具体的任务"""
        pass
    
    @classmethod
    async def _run(
        cls,
        db: IndexedRocksDB,
        max_concurrent_tasks: int,
        **kwargs
    ):
        """运行任务循环"""
        task_id = cls.get_task_id()
        logger = cls._loggers.get(task_id)
        
        cls._pending_tasks[task_id] = set()
        
        try:
            while not cls._stop_events[task_id].is_set():
                try:
                    # 清理已完成的任务
                    done_tasks = {t for t in cls._pending_tasks[task_id] if t.done()}
                    for task in done_tasks:
                        try:
                            await task
                        except Exception as e:
                            logger.error(f"任务执行错误: {e}")
                            await asyncio.sleep(cls._sleep_time_on_error)
                    cls._pending_tasks[task_id].difference_update(done_tasks)
                    
                    # 检查是否可以创建新任务
                    while len(cls._pending_tasks[task_id]) < max_concurrent_tasks:
                        todo_task = await cls.fetch_todo_task(db, **kwargs)
                        if not todo_task:
                            break
                            
                        # 创建异步任务
                        async def process_wrapper(task):
                            try:
                                await cls.task_to_processing(db, task)
                                await cls.process_todo_task(db, task, **kwargs)
                            except Exception as e:
                                logger.error(f"任务处理失败: {e}")
                                await asyncio.sleep(cls._sleep_time_on_error)

                        task = asyncio.create_task(process_wrapper(todo_task), name=f"{task_id}-{todo_task}")
                        cls._pending_tasks[task_id].add(task)
                    
                    # 如果没有任务，等待一段时间
                    if not cls._pending_tasks[task_id]:
                        await asyncio.sleep(cls._sleep_time_when_idle)
                    else:
                        # 短暂等待，让其他任务有机会执行
                        await asyncio.sleep(0)
                        
                except Exception as e:
                    logger.error(f"任务循环发生错误: {e}")
                    await asyncio.sleep(cls._sleep_time_on_error)
                    
        finally:
            if cls._pending_tasks.get(task_id):
                logger.debug("等待所有任务完成...")
                pending = cls._pending_tasks[task_id]
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            cls._pending_tasks[task_id] = set()
    
    @classmethod
    def start(
        cls,
        db: IndexedRocksDB,
        max_concurrent_tasks: int = None,
        logger: Optional[logging.Logger] = None,
        **kwargs: Any
    ) -> None:
        """启动任务
        
        Args:
            db: RocksDB实例
            sleep_time: 轮询间隔时间(秒)
            logger: 日志记录器
            **kwargs: 传递给 _process_task 的额外参数
        """
        if max_concurrent_tasks is None:
            max_concurrent_tasks = 5
        
        if not isinstance(max_concurrent_tasks, int) or max_concurrent_tasks <= 0:
            raise ValueError("max_concurrent_tasks 必须是大于 0 的整数")
            
        task_id = cls.get_task_id()
        
        if cls._instances.get(task_id) is not None:
            raise RuntimeError(f"{cls.__name__} 已经在运行")
        
        # 初始化任务相关变量
        cls._instances[task_id] = cls
        cls._stop_events[task_id] = asyncio.Event()
        cls._loggers[task_id] = logger or logging.getLogger(cls.__name__)
        
        # 创建异步任务
        async_utils = AsyncUtils()
        loop = async_utils.get_or_create_loop()
        
        # 启动后台任务
        cls._server_tasks[task_id] = loop.create_task(
            cls._run(db, max_concurrent_tasks, **kwargs)
        )
        
        cls._loggers[task_id].debug(f"{cls.__name__} 开始运行")
    
    @classmethod
    async def stop(cls) -> None:
        """停止任务"""
        task_id = cls.get_task_id()
        
        if task_id not in cls._instances or cls._instances[task_id] is None:
            return
            
        if cls._stop_events.get(task_id):
            cls._stop_events[task_id].set()
        
        # 等待主任务和所有pending任务完成
        if cls._server_tasks.get(task_id):
            cls._server_tasks[task_id].cancel()
            try:
                await cls._server_tasks[task_id]
            except asyncio.CancelledError:
                pass
            finally:
                cls._server_tasks[task_id] = None
                cls._instances[task_id] = None
                cls._loggers[task_id].debug(f"{cls.__name__} 已停止") 