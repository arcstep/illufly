from typing import Any, Callable, Dict, Optional
import hashlib
import json
from pydantic import BaseModel, Field
import pickle
from datetime import datetime

from ..envir.default_env import get_env
from ..io.rocksdict import BaseRocksDB

CACHE_DB = BaseRocksDB(get_env("ILLUFLY_CACHE_CALL"))

class CallContext(BaseModel):
    """调用上下文，支持任意键值对"""
    context: Dict[str, Any] = Field(default_factory=dict)
    
    def get_cache_key(self) -> str:
        """生成上下文的缓存键"""
        # 对字典进行排序以确保相同内容生成相同的键
        return hashlib.sha256(
            json.dumps(self.context, sort_keys=True).encode()
        ).hexdigest()

class CachedResult(BaseModel):
    """缓存的结果"""
    result: Any
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    is_error: bool = False
    result_type: Optional[str] = None  # 添加类型信息

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化"""
        try:
            if self.result is not None:
                result_type = f"{self.result.__class__.__module__}.{self.result.__class__.__name__}"
                return {
                    "result": pickle.dumps(self.result).hex(),
                    "result_type": result_type,
                    "error": self.error,
                    "timestamp": self.timestamp.isoformat(),
                    "is_error": self.is_error
                }
            return {
                "result": None,
                "error": self.error,
                "timestamp": self.timestamp.isoformat(),
                "is_error": self.is_error
            }
        except Exception as e:
            raise ValueError(f"无法序列化结果: {str(e)}")

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> "CachedResult":
        """自定义反序列化"""
        if data.get("result"):
            try:
                result = pickle.loads(bytes.fromhex(data["result"]))
                return cls(
                    result=result,
                    error=data.get("error"),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    is_error=data.get("is_error", False),
                    result_type=data.get("result_type")
                )
            except Exception as e:
                raise ValueError(f"无法反序列化结果: {str(e)}")
        return cls(
            result=None,
            error=data.get("error"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_error=data.get("is_error", False)
        )

def call_with_cache(
    func: Callable,
    *args,
    context: CallContext,
    **kwargs
) -> Any:
    """支持对通用函数调用实现缓存支持"""
    # 生成缓存键
    args_key = hashlib.sha256(str(args).encode()).hexdigest()
    kwargs_key = hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()
    context_key = context.get_cache_key()
    cache_key = f"{func.__module__}.{func.__name__}.{context_key}.{args_key}.{kwargs_key}"
    
    # 检查缓存是否存在
    exists, value = CACHE_DB.may_exist(cache_key)
    if exists and value is not None:
        cached = CachedResult.model_validate(value)
        if cached and cached.is_error:  # 确保 cached 不为 None
            raise RuntimeError(cached.error)
        return cached.result if cached else None
    
    # 执行调用
    try:
        result = func(*args, **kwargs)
        cached = CachedResult(
            result=result,
            is_error=False
        )
    except Exception as e:
        # 确保异常被正确捕获并存储
        error_msg = str(e)
        cached = CachedResult(
            result=None,
            error=error_msg,
            is_error=True
        )
        # 存储错误结果
        CACHE_DB.put(cache_key, cached.model_dump())
        # 重新抛出异常
        raise RuntimeError(error_msg)
    
    # 存储成功结果
    CACHE_DB.put(cache_key, cached.model_dump())
    return cached.result


