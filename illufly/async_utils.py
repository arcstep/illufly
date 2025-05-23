import asyncio
import logging
from typing import Optional, Any, AsyncGenerator, Generator, TypeVar, Callable, Awaitable
from contextlib import contextmanager, asynccontextmanager
from functools import wraps

T = TypeVar('T')

class AsyncUtils:
    """异步环境管理基类
    
    专注于处理：
    1. 事件循环管理（创建、嵌套、清理）
    2. 任务生命周期（创建、跟踪、清理）
    3. 异步/同步转换
    """
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._tasks = set()
        self._cleanup_lock = asyncio.Lock()
        self._logger.debug(f"AsyncUtils created: {id(self)}")
        
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
        try:
            current_task = asyncio.current_task()
            
            async with self._cleanup_lock:
                active_tasks = [
                    t 
                    for t in self._tasks
                    if not t.done() and t != current_task
                ]
                
                if not active_tasks:
                    return
                    
                for task in active_tasks:
                    task.cancel()
                    try:
                        await asyncio.wait([task], timeout=0.1)
                    except Exception as e:
                        self._logger.error(f"Error cleaning up task: {e}")
                    finally:
                        if task in self._tasks:
                            self._tasks.remove(task)
                            
                self._logger.debug(f"Cleanup completed, remaining tasks: {len(self._tasks)}")
        except RuntimeError as e:
            if "no running event loop" in str(e):
                self._logger.debug("Skipping cleanup as no event loop is running")
            else:
                self._logger.error(f"Runtime error during cleanup: {e}")
        except Exception as e:
            self._logger.error(f"Unexpected error during cleanup: {e}")

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
        async def managed_agen():
            try:
                async for item in agen:
                    yield item
            finally:
                await self._cleanup_tasks()
                
        ait = managed_agen()
        loop = self.get_or_create_loop()
        while True:
            try:
                yield loop.run_until_complete(ait.__anext__())
            except StopAsyncIteration:
                self._logger.debug(f"Generator finished with loop: {id(loop)}, is_closed={loop.is_closed()}")
                break
            except Exception as e:
                self._logger.error(f"Error in generator with loop: {id(loop)}, error: {e}")
                raise

    def wrap_sync_func(self, func: Callable[..., T]) -> Callable[..., Awaitable[T]]:
        """将同步函数包装为异步函数"""
        async def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper

    def wrap_async_func(self, func: Callable[..., Awaitable[T]]) -> Callable[..., T]:
        """将异步函数包装为同步函数"""
        def wrapper(*args, **kwargs):
            loop = self.get_or_create_loop()
            return loop.run_until_complete(func(*args, **kwargs))
        return wrapper 