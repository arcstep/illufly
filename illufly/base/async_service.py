import asyncio
import logging
from typing import Optional, Any, AsyncGenerator, Generator, TypeVar, Callable
from contextlib import contextmanager, asynccontextmanager
from functools import wraps

T = TypeVar('T')

class AsyncService:
    """异步环境管理基类
    
    专注于处理：
    1. 事件循环管理（创建、嵌套、清理）
    2. 任务生命周期（创建、跟踪、清理）
    3. 异步/同步转换
    """
    def __init__(self, logger: Optional[logging.Logger] = None):
        self._logger = logger or logging.getLogger(__name__)
        self._tasks = set()
        self._cleanup_lock = asyncio.Lock()
        
    @staticmethod
    def get_or_create_loop() -> asyncio.AbstractEventLoop:
        """获取或创建事件循环，自动处理嵌套情况"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
            
    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        """跟踪任务生命周期"""
        self._tasks.add(task)
        self._logger.debug(f"Task tracked: {task.get_name()}")
        
        def cleanup_callback(t):
            self._tasks.discard(t)
            self._logger.debug(f"Task untracked: {t.get_name()}")
            
        task.add_done_callback(cleanup_callback)
        return task
        
    async def _cleanup_tasks(self):
        """清理所有跟踪的任务，除了当前任务"""
        current_task = asyncio.current_task()
        
        async with self._cleanup_lock:
            active_tasks = [t for t in self._tasks 
                          if not t.done() and t != current_task]
            
            if not active_tasks:
                return
                
            self._logger.debug(f"Cleaning up {len(active_tasks)} tasks")
            for task in active_tasks:
                task.cancel()
                try:
                    await asyncio.wait([task], timeout=0.1)
                    if not task.done():
                        self._logger.warning(f"Task {task.get_name()} failed to cancel in time")
                    elif task.cancelled():
                        self._logger.debug(f"Task cancelled: {task.get_name()}")
                    else:
                        self._logger.debug(f"Task completed: {task.get_name()}")
                except Exception as e:
                    self._logger.error(f"Error cleaning up task: {e}")

    def to_sync(self, async_func: Callable[..., T]) -> Callable[..., T]:
        """装饰器：将异步函数转换为同步函数"""
        @wraps(async_func)
        def wrapper(*args, **kwargs):
            loop = self.get_or_create_loop()
            return loop.run_until_complete(async_func(*args, **kwargs))
        return wrapper
        
    @asynccontextmanager
    async def managed_async(self):
        """异步上下文管理器：自动跟踪和清理任务"""
        task = asyncio.current_task()
        if task:
            self._track_task(task)
            self._logger.debug(f"Managing async task: {task.get_name()}")
        try:
            yield
        finally:
            # 清理其他任务，但不包括当前任务
            await self._cleanup_tasks()
            if task:
                self._logger.debug(f"Async task completed: {task.get_name()}")
            
    @contextmanager
    def managed_sync(self):
        """同步上下文管理器：自动处理事件循环和任务清理"""
        loop = self.get_or_create_loop()
        try:
            yield loop
        finally:
            loop.run_until_complete(self._cleanup_tasks())
            
    def wrap_async_generator(self, agen: AsyncGenerator[T, None]) -> Generator[T, None, None]:
        """包装异步生成器为同步生成器"""
        loop = self.get_or_create_loop()
        
        async def managed_agen():
            async with self.managed_async():
                async for item in agen:
                    yield item
                    
        ait = managed_agen()
        try:
            while True:
                try:
                    yield loop.run_until_complete(ait.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            loop.run_until_complete(self._cleanup_tasks()) 