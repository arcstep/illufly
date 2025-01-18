from typing import Any, Callable, Dict, Optional, AsyncIterator, Iterator, Union
from pydantic import BaseModel, Field
from datetime import datetime

import hashlib
import json
import logging
import pickle

from ..envir.default_env import get_env
from ..io.rocksdict import BaseRocksDB

class CacheDBManager:
    _db = None

    @classmethod
    def get_db(cls):
        if cls._db is None:
            cls._db = BaseRocksDB(get_env("ILLUFLY_CACHE_CALL"))
        return cls._db

    @classmethod
    def reset_db(cls):
        if cls._db is not None:
            cls._db.close()
            cls._db = None

# 替换全局变量
def get_cache_db():
    return CacheDBManager.get_db()

logger = logging.getLogger(__name__)

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
    result_type: Optional[str] = None
    is_iterator: bool = False

    def model_dump(self) -> Dict[str, Any]:
        """自定义序列化"""
        try:
            if self.result is not None:
                result_type = f"{self.result.__class__.__module__}.{self.result.__class__.__name__}"
                
                # 处理迭代器
                if isinstance(self.result, Iterator):
                    self.result = list(self.result)
                    self.is_iterator = True
                
                return {
                    "result": pickle.dumps(self.result).hex(),
                    "result_type": result_type,
                    "error": self.error,
                    "timestamp": self.timestamp.isoformat(),
                    "is_error": self.is_error,
                    "is_iterator": self.is_iterator,
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
                
                # 如果原结果是迭代器，返回一个新的迭代器
                if data.get("is_iterator"):
                    result = iter(result)
                
                return cls(
                    result=result,
                    error=data.get("error"),
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    is_error=data.get("is_error", False),
                    result_type=data.get("result_type"),
                    is_iterator=data.get("is_iterator", False),
                )
            except Exception as e:
                raise ValueError(f"无法反序列化结果: {str(e)}")
        return cls(
            result=None,
            error=data.get("error"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            is_error=data.get("is_error", False)
        )

def _generate_cache_key(func: Callable, context: CallContext, args: tuple, kwargs: dict) -> str:
    """生成缓存键"""
    params = {"args": args, "kwargs": kwargs}
    params_key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    context_key = context.get_cache_key()
    return f"{func.__module__}.{func.__name__}.{context_key}.{params_key}"

def _get_cached_result(cache_key: str, context: CallContext, params: dict, logger: logging.Logger) -> Optional[CachedResult]:
    """获取缓存的结果"""
    exists, value = get_cache_db().may_exist(cache_key)
    if exists and value is not None:
        cached = CachedResult.model_validate(value)
        logger.info(f"Cache hit for {cache_key}, with context: {context.context}, params: {params}")
        return cached
    return None

def _handle_error(error: Exception, cache_key: str) -> None:
    """处理和缓存错误"""
    error_msg = str(error)
    cached = CachedResult(
        result=None,
        error=error_msg,
        is_error=True
    )
    get_cache_db().put(cache_key, cached.model_dump())
    raise RuntimeError(error_msg)

def call_with_cache(
    func: Callable,
    *args,
    context: CallContext,
    logger: logging.Logger = None,
    **kwargs
) -> Any:
    """支持对通用函数调用实现缓存支持"""
    logger = logger or logging.getLogger(__name__)
    cache_key = _generate_cache_key(func, context, args, kwargs)
    
    # 检查缓存
    if cached := _get_cached_result(cache_key, context, {"args": args, "kwargs": kwargs}, logger):
        logger.warning(f"Cache hit for {cache_key}, with context: {context}, params: {kwargs}")
        if cached.is_error:
            raise RuntimeError(cached.error)
        if cached.is_iterator:
            return iter(cached.result)
        return cached.result
    
    # 执行调用
    try:
        result = func(*args, **kwargs)
        if isinstance(result, Iterator):
            result = list(result)
            cached = CachedResult(
                result=result,
                is_error=False,
                is_iterator=True
            )
        elif isinstance(result, AsyncIterator):
            raise ValueError("缓存不支持异步迭代器")
        else:
            cached = CachedResult(
                result=result,
                is_error=False
            )
        # 存储结果
        get_cache_db().put(cache_key, cached.model_dump())
        if cached.is_iterator:
            return iter(result)
        return cached.result
    except Exception as e:
        _handle_error(e, cache_key)


