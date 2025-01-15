import asyncio
import logging
from typing import Any, Callable, Optional, Union, Awaitable
import sys
import inspect

from .async_service import AsyncService

class BaseCall():
    """支持兼容同步方法或异步方法定义的基类服务"""
    def __init__(self, logger: logging.Logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._async_service = AsyncService(self._logger)

    def _is_jupyter_cell(self):
        """检查是否在 Jupyter 单元格中运行"""
        try:
            frame = inspect.currentframe()
            while frame:
                filename = frame.f_code.co_filename
                self._logger.debug(f"Checking frame filename: {filename}")
                
                # 检查是否在 IPython/Jupyter 环境中
                if ('ipykernel' in filename or 
                    'IPython' in filename or 
                    filename.startswith('<ipython-input-') or
                    filename.startswith('/tmp/ipykernel_') or
                    filename.startswith('/var/folders') and 'ipykernel' in filename):
                    self._logger.debug(f"Found Jupyter environment in {filename}")
                    return True
                frame = frame.f_back
            return False
        finally:
            if frame:
                del frame

    def _is_async_context(self):
        """检查是否在真正的异步上下文中"""
        frame = None
        try:
            # 检查调用栈中是否有用户定义的 async 函数
            frame = inspect.currentframe()
            while frame:
                is_coro = bool(frame.f_code.co_flags & inspect.CO_COROUTINE)
                func_name = frame.f_code.co_name
                filename = frame.f_code.co_filename
                
                self._logger.debug(f"Checking frame: {func_name} in {filename} (is_coro: {is_coro})")
                
                # 如果是用户定义的异步函数，返回 True
                # 排除系统库的异步函数
                if is_coro and not any(x in filename for x in [
                    'asyncio', 'tornado', 
                    'interactiveshell.py', 'kernelapp.py'
                ]):
                    self._logger.debug(f"Found user async function: {func_name} in {filename}")
                    return True
                frame = frame.f_back
            
            # 在 Jupyter 环境中，只有在用户定义的异步函数中才返回 True
            if self._is_jupyter_cell():
                self._logger.debug("In Jupyter but no user async function found")
                return False
                
            # 非 Jupyter 环境，检查是否有事件循环
            try:
                loop = asyncio.get_running_loop()
                self._logger.debug("Found event loop in non-Jupyter environment")
                return True
            except RuntimeError:
                self._logger.debug("No event loop found")
                return False
            
        finally:
            if frame:
                del frame

    def _get_handler_mode(self, sync_handler: Optional[Callable] = None, 
                         async_handler: Optional[Callable] = None,
                         base_class: Optional[type] = None) -> str:
        """检测处理方法的模式"""
        def is_method_overridden(method: Optional[Callable], base: Optional[type]) -> bool:
            if method is None:
                return False
            if base is None:
                return True
                
            # 获取方法在基类中的定义
            base_method = getattr(base, method.__name__, None)
            if base_method is None:
                return True
                
            # 获取实际的函数对象
            if hasattr(method, '__func__'):  # 绑定方法
                method = method.__func__
            if hasattr(base_method, '__func__'):  # 绑定方法
                base_method = base_method.__func__
                
            # 比较函数的代码对象
            return method.__code__ is not base_method.__code__
            
        # 如果没有提供处理方法，使用默认的方法名
        if sync_handler is None and async_handler is None:
            sync_handler = getattr(self, 'handle_call', None)
            async_handler = getattr(self, 'async_handle_call', None)
            base_class = BaseCall  # 使用 BaseCall 作为默认基类
            
        has_sync = sync_handler is not None and not asyncio.iscoroutinefunction(sync_handler) \
                  and is_method_overridden(sync_handler, base_class)
        has_async = async_handler is not None and asyncio.iscoroutinefunction(async_handler) \
                   and is_method_overridden(async_handler, base_class)
        
        if has_sync and has_async:
            return 'both'
        elif has_sync:
            return 'sync'
        elif has_async:
            return 'async'
        else:
            raise NotImplementedError("Neither sync nor async handler is provided")
            
    def auto_call(self, sync_func, async_func, base_class=None):
        """自动选择同步或异步函数"""
        if sync_func is None and async_func is None:
            raise NotImplementedError("Neither sync nor async handler is provided")
            
        async def async_wrapper(*args, **kwargs):
            """异步包装器"""
            if async_func is not None and self._get_handler_mode(sync_func, async_func, base_class) in ('async', 'both'):
                return await async_func(*args, **kwargs)
            elif sync_func is not None:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(None, sync_func, *args)
            else:
                raise NotImplementedError("No suitable handler for async context")

        def wrapper(*args, **kwargs):
            is_async = self._is_async_context()
            is_jupyter = self._is_jupyter_cell()
            self._logger.debug(f"Context detection - async: {is_async}, jupyter: {is_jupyter}")
            
            # 使用 base_class 检查方法重写
            handler_mode = self._get_handler_mode(sync_func, async_func, base_class)
            self._logger.debug(f"Handler mode: {handler_mode}")
            
            if is_async:
                # 在异步上下文中，优先使用异步处理器
                if async_func is not None and handler_mode in ('async', 'both'):
                    return async_wrapper(*args, **kwargs)
                elif sync_func is not None and handler_mode in ('sync', 'both'):
                    # 在异步上下文中也允许使用同步处理器
                    loop = asyncio.get_running_loop()
                    return loop.run_in_executor(None, sync_func, *args)
                else:
                    raise NotImplementedError("No suitable handler for async context")
            else:
                if sync_func is not None and handler_mode in ('sync', 'both'):
                    return sync_func(*args, **kwargs)
                elif async_func is not None:
                    loop = asyncio.new_event_loop()
                    try:
                        return loop.run_until_complete(async_func(*args, **kwargs))
                    finally:
                        loop.close()
                else:
                    raise NotImplementedError("No suitable handler for sync context")
                        
        return wrapper

    def __call__(self, *args, **kwargs) -> Any:
        """默认调用方法，使用默认的处理方法名"""
        return self.auto_call(
            self.handle_call,
            self.async_handle_call,
            base_class=BaseCall
        )(*args, **kwargs)

    def handle_call(self, *args, **kwargs) -> Any:
        """同步处理请求"""
        raise NotImplementedError

    async def async_handle_call(self, *args, **kwargs) -> Any:
        """异步处理请求"""
        raise NotImplementedError
