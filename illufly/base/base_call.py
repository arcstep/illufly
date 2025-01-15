import asyncio
import logging
from typing import Any

from .async_service import AsyncService

class BaseCall():
    """支持兼容同步方法或异步方法定义的基类服务"""
    def __init__(self, logger: logging.Logger=None):
        self._logger = logger or logging.getLogger(__name__)

    def handle_request(self, *args, **kwargs) -> Any:
        """同步处理请求"""
        raise NotImplementedError

    async def async_handle_request(self, *args, **kwargs) -> Any:
        """异步处理请求"""
        raise NotImplementedError

    def _is_async_context(self) -> bool:
        """检测是否在异步上下文中"""
        try:
            loop = asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
            
    def _get_handler_mode(self) -> str:
        """检测子类实现了哪种处理方法
        
        检查整个继承链，只要不是 BaseCall 中的方法就认为是有效实现
        """
        def is_method_overridden(method_name: str) -> bool:
            # 获取当前类的方法
            method = getattr(self.__class__, method_name, None)
            if method is None:
                return False
            # 获取 BaseCall 的方法
            base_method = getattr(BaseCall, method_name, None)
            # 如果方法存在且不等于基类方法，则认为被重写
            return method is not None and method != base_method

        has_sync = is_method_overridden('handle_request')
        has_async = is_method_overridden('async_handle_request')
        
        if has_sync and has_async:
            return 'both'
        elif has_sync:
            return 'sync'
        elif has_async:
            return 'async'
        else:
            raise NotImplementedError("Neither handle_request nor async_handle_request is implemented")
            
    def __call__(self, *args, **kwargs) -> Any:
        """智能调用入口，根据上下文和实现方式自动选择调用方式"""
        handler_mode = self._get_handler_mode()
        is_async_ctx = self._is_async_context()
        
        if is_async_ctx:
            self._logger.debug("Detected async context")
            if handler_mode in ('async', 'both'):
                return self.call_async(*args, **kwargs)
            else:  # sync only
                async_service = AsyncService(self._logger)
                return async_service.wrap_sync_func(
                    lambda: self.call(*args, **kwargs)
                )()  # 直接调用，因为wrap_sync_func返回异步函数
        else:
            self._logger.debug("Detected sync context")
            if handler_mode in ('sync', 'both'):
                return self.call(*args, **kwargs)
            else:  # async only
                async_service = AsyncService(self._logger)
                return async_service.wrap_async_func(
                    lambda: self.call_async(*args, **kwargs)
                )()  # 直接调用，因为wrap_async_func返回同步函数

    def call(self, *args, **kwargs) -> Any:
        """同步调用实现"""
        if self._get_handler_mode() == 'async':
            async_service = AsyncService(self._logger)
            return async_service.wrap_async_func(
                lambda: self.async_handle_request(*args, **kwargs)
            )()  # 直接调用
        return self.handle_request(*args, **kwargs)

    async def call_async(self, *args, **kwargs) -> Any:
        """异步调用实现"""
        if self._get_handler_mode() == 'sync':
            async_service = AsyncService(self._logger)
            wrapped = async_service.wrap_sync_func(
                lambda: self.handle_request(*args, **kwargs)
            )
            return await wrapped()  # 等待异步函数执行完成
        return await self.async_handle_request(*args, **kwargs)
