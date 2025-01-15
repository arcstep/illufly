import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Tuple, Union

class BaseCall:
    """支持同步异步方法互转的基类"""
    def __init__(self, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)
        self._methods: Dict[str, Tuple[Optional[Callable], Optional[Callable]]] = {}
        
    def register_methods(
        self,
        method_name: str,
        sync_handle: Optional[Callable] = None,
        async_handle: Optional[Callable] = None
    ) -> None:
        """注册方法对
        Args:
            method_name: 方法名
            sync_handle: 同步方法
            async_handle: 异步方法
        """
        if sync_handle is None and async_handle is None:
            raise ValueError("At least one of sync_handle or async_handle must be provided")
            
        if sync_handle and asyncio.iscoroutinefunction(sync_handle):
            raise ValueError("sync_handle must be a synchronous function")
            
        if async_handle and not asyncio.iscoroutinefunction(async_handle):
            raise ValueError("async_handle must be an asynchronous function")
            
        self._methods[method_name] = (sync_handle, async_handle)
        
    def sync_call(self, method_name: str, *args, **kwargs) -> Any:
        """同步调用
        Args:
            method_name: 要调用的方法名
            *args, **kwargs: 传递给方法的参数
        """
        if method_name not in self._methods:
            raise KeyError(f"Method {method_name} not registered")
            
        sync_handle, async_handle = self._methods[method_name]
        
        if sync_handle:
            return sync_handle(*args, **kwargs)
        elif async_handle:
            def run_async():
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    return loop.run_until_complete(async_handle(*args, **kwargs))
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
            
            # 处理嵌套事件循环的情况
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果当前线程有事件循环在运行，使用线程池执行
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(run_async)
                        return future.result()
                else:
                    # 如果事件循环未运行，直接执行
                    return run_async()
            except RuntimeError:
                # 如果没有事件循环，直接执行
                return run_async()
                
    async def async_call(self, method_name: str, *args, **kwargs) -> Any:
        """异步调用
        Args:
            method_name: 要调用的方法名
            *args, **kwargs: 传递给方法的参数
        """
        if method_name not in self._methods:
            raise KeyError(f"Method {method_name} not registered")
            
        sync_handle, async_handle = self._methods[method_name]
        
        if async_handle:
            return await async_handle(*args, **kwargs)
        elif sync_handle:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, sync_handle, *args, **kwargs)
