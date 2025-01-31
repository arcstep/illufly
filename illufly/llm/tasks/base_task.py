from typing import Optional, ClassVar, Any
from abc import ABC, abstractmethod
import asyncio
import logging

from ...async_utils import AsyncUtils
from ...io.rocksdict import IndexedRocksDB

class BaseTask(ABC):
    """异步任务基类"""
    
    _instances: ClassVar[dict] = {}  # 存储不同任务类型的实例
    _stop_events: ClassVar[dict] = {}  # 存储不同任务的停止事件
    _server_tasks: ClassVar[dict] = {}  # 存储不同任务的服务任务
    _loggers: ClassVar[dict] = {}  # 存储不同任务的日志记录器
    
    def __init__(self):
        raise RuntimeError(f"请使用 {self.__class__.__name__}.start() 启动任务")
    
    @classmethod
    def get_task_id(cls) -> str:
        """获取任务ID，默认使用类名"""
        return cls.__name__
    
    @classmethod
    @abstractmethod
    async def _process_batch(cls, db: IndexedRocksDB, **kwargs) -> None:
        """处理一批任务，由子类实现"""
        pass
    
    @classmethod
    async def _run(cls, db: IndexedRocksDB, sleep_time: float, **kwargs):
        """运行任务循环"""
        task_id = cls.get_task_id()
        logger = cls._loggers.get(task_id)
        
        try:
            while not cls._stop_events[task_id].is_set():
                try:
                    await cls._process_batch(db, **kwargs)
                    await asyncio.sleep(sleep_time)
                except Exception as e:
                    logger.error(f"任务循环发生错误: {e}", exc_info=True)
                    await asyncio.sleep(sleep_time)
        finally:
            cls._instances[task_id] = None
            logger.info(f"{cls.__name__} 结束运行")
    
    @classmethod
    def start(
        cls,
        db: IndexedRocksDB,
        sleep_time: float = 1.0,
        logger: Optional[logging.Logger] = None,
        **kwargs: Any
    ) -> None:
        """启动任务
        
        Args:
            db: RocksDB实例
            sleep_time: 轮询间隔时间(秒)
            logger: 日志记录器
            **kwargs: 传递给 _process_batch 的额外参数
        """
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
            cls._run(db, sleep_time, **kwargs)
        )
        
        cls._loggers[task_id].info(f"{cls.__name__} 开始运行")
    
    @classmethod
    async def stop(cls) -> None:
        """停止任务"""
        task_id = cls.get_task_id()
        
        if task_id not in cls._instances or cls._instances[task_id] is None:
            return
            
        if cls._stop_events.get(task_id):
            cls._stop_events[task_id].set()
        
        if cls._server_tasks.get(task_id):
            cls._server_tasks[task_id].cancel()
            try:
                await cls._server_tasks[task_id]
            except asyncio.CancelledError:
                pass
            finally:
                cls._server_tasks[task_id] = None
                cls._instances[task_id] = None
                cls._loggers[task_id].info(f"{cls.__name__} 已停止") 