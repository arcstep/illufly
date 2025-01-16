import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Tuple, Union
from functools import partial

class BaseCall:
    """支持同步异步方法互转的基类"""
    def __init__(self, logger: logging.Logger = None):
        self._logger = logger or logging.getLogger(__name__)
        self._methods: Dict[str, Tuple[Optional[Callable], Optional[Callable]]] = {}
        
    def register_method(
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
        
    def sync_method(self, method_name: str, *args, **kwargs) -> Any:
        """同步调用方法
        
        优先使用同步方法，如果没有同步方法才使用异步方法。
        """
        if method_name not in self._methods:
            raise KeyError(f"Method {method_name} not registered")
            
        sync_handle, async_handle = self._methods[method_name]
        
        # 优先使用同步方法
        if sync_handle:
            return sync_handle(*args, **kwargs)
        elif async_handle:
            loop = asyncio.get_event_loop()
            self._logger.debug(f"sync_method using loop: {id(loop)}, is_closed={loop.is_closed()}, is_running={loop.is_running()}")
            
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                self._logger.debug("Applied nest_asyncio for running loop")
                
            result = loop.run_until_complete(async_handle(*args, **kwargs))
            self._logger.debug(f"sync_method finished with loop: {id(loop)}, is_closed={loop.is_closed()}")
            return result
                
    async def async_method(self, method_name: str, *args, **kwargs) -> Any:
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
            # 使用 partial 将关键字参数绑定到函数
            bound_handle = partial(sync_handle, **kwargs)
            return await loop.run_in_executor(None, bound_handle, *args)
