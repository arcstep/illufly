import asyncio
import logging
from typing import Any, Callable, Optional, Union, Awaitable

from .async_service import AsyncService

class BaseCall():
    """支持兼容同步方法或异步方法定义的基类服务"""
    def __init__(self, logger: logging.Logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._async_service = AsyncService(self._logger)

    def _is_async_context(self) -> bool:
        """检测是否在异步上下文中"""
        try:
            loop = asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
            
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
            
    def auto_call(self, 
                 sync_handler: Optional[Callable[..., Any]],
                 async_handler: Optional[Callable[..., Awaitable[Any]]],
                 base_class: Optional[type] = None,
                 ) -> Callable[..., Union[Any, Awaitable[Any]]]:
        """自动调度同步或异步处理方法
        
        Args:
            sync_handler: 同步处理方法
            async_handler: 异步处理方法
            base_class: 基类，用于判断方法是否被重写
            
        Returns:
            根据上下文返回适当的调用包装器
        """
        handler_mode = self._get_handler_mode(sync_handler, async_handler, base_class)
        is_async_ctx = self._is_async_context()
        
        def make_sync_call(*args, **kwargs):
            """构造同步调用"""
            if handler_mode in ('sync', 'both'):
                return sync_handler(*args, **kwargs)
            else:  # async only
                return self._async_service.wrap_async_func(
                    lambda: async_handler(*args, **kwargs)
                )()
                
        async def make_async_call(*args, **kwargs):
            """构造异步调用"""
            if handler_mode in ('async', 'both'):
                return await async_handler(*args, **kwargs)
            else:  # sync only
                wrapped = self._async_service.wrap_sync_func(
                    lambda: sync_handler(*args, **kwargs)
                )
                return await wrapped()
                
        def wrapper(*args, **kwargs):
            """根据上下文选择调用方式"""
            if is_async_ctx:
                self._logger.debug("Detected async context")
                return make_async_call(*args, **kwargs)
            else:
                self._logger.debug("Detected sync context")
                return make_sync_call(*args, **kwargs)
                
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
