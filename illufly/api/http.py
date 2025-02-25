from functools import wraps
from inspect import signature, Parameter
import logging
from typing import get_type_hints
from fastapi import HTTPException, status

def handle_errors(logger: logging.Logger = None):
    """保留函数签名的异常处理装饰器"""
    def decorator(func):
        # 保留原始签名信息
        func_sig = signature(func)
        type_hints = get_type_hints(func)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                local_logger = logger or logging.getLogger(func.__module__)
                local_logger.error(
                    f"处理 {func.__name__} 时发生未捕获异常",
                    exc_info=True,
                    extra={"endpoint": func.__name__}
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="服务器内部错误"
                )

        # 手动同步参数信息
        wrapper.__signature__ = func_sig.replace(
            parameters=[
                param.replace(kind=Parameter.KEYWORD_ONLY)
                if param.kind == param.POSITIONAL_OR_KEYWORD 
                else param
                for param in func_sig.parameters.values()
            ]
        )
        wrapper.__annotations__ = type_hints
        
        return wrapper
    return decorator