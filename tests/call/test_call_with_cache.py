import pytest
import os
import shutil
from pathlib import Path
from datetime import datetime
from illufly.base import CallContext, CachedResult, call_with_cache
from openai import OpenAI
from unittest.mock import Mock, patch
from dataclasses import dataclass
from typing import Dict, List, Any

@pytest.fixture(scope="module", autouse=True)
def cache_dir(tmp_path_factory):
    """设置测试缓存目录，自动应用于所有测试"""
    # 使用 pytest 的临时目录工厂创建模块级别的临时目录
    cache_dir = tmp_path_factory.mktemp("illufly_cache")
    
    # 如果环境变量存在，则使用环境变量指定的路径
    if cache_path := os.getenv("ILLUFLY_CACHE_CALL"):
        cache_dir = Path(cache_path)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        cache_dir.mkdir(parents=True)
    
    # 设置缓存目录
    os.environ["ILLUFLY_CACHE_CALL"] = str(cache_dir)
    
    yield cache_dir
    
    # 测试后清理
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

@pytest.fixture(scope="module")
def openai_client():
    return OpenAI()

def test_call_context():
    """测试调用上下文"""
    context = CallContext(context={
        "base_url": "https://api.test.com",
        "provider": "OPENAI"
    })
    
    # 验证缓存键不包含敏感信息
    cache_key = context.get_cache_key()
    assert "test_key" not in cache_key

def test_cached_result_serialization():
    """测试结果序列化"""
    # 测试普通对象
    result = {"test": "data"}
    cached = CachedResult(result=result)
    data = cached.model_dump()
    restored = CachedResult.model_validate(data)
    assert restored.result == result
    
    # 测试不可序列化对象
    with pytest.raises(ValueError):
        CachedResult(result=lambda x: x).model_dump()

@pytest.mark.asyncio
async def test_openai_cache():
    """测试 OpenAI 调用缓存"""
    def mock_create(*args, **kwargs):
        return {
            "choices": [{
                "message": {
                    "content": "Test response",
                    "role": "assistant"
                },
                "finish_reason": "stop"
            }],
            "model": "gpt-4",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }
    
    # 设置函数属性
    mock_create.__name__ = 'create'
    mock_create.__module__ = 'openai.resources.chat.completions'
    
    context = CallContext(context={
        "base_url": "https://api.test.com",
        "provider": "OPENAI"
    })
    
    # 第一次调用
    result1 = call_with_cache(
        mock_create,
        messages=[{"role": "user", "content": "test"}],
        context=context
    )
    
    # 第二次调用应该返回缓存结果
    result2 = call_with_cache(
        mock_create,
        messages=[{"role": "user", "content": "test"}],
        context=context
    )
    
    assert result1 == result2
    assert result1["choices"][0]["message"]["content"] == "Test response"

@pytest.mark.asyncio
async def test_error_caching():
    """测试错误缓存"""
    def failing_func(*args, **kwargs):
        raise Exception("API Error")
    
    # 设置函数属性
    failing_func.__name__ = 'failing_func'
    failing_func.__module__ = 'test_module'
    
    context = CallContext(context={
        "base_url": "https://api.test.com",
        "provider": "OPENAI"
    })
    
    # 第一次调用应该抛出错误
    with pytest.raises(RuntimeError) as exc_info:
        call_with_cache(
            failing_func,
            messages=[{"role": "user", "content": "test"}],
            context=context
        )
    assert "API Error" in str(exc_info.value)
    
    # 第二次调用应该返回缓存的错误
    with pytest.raises(RuntimeError) as exc_info:
        call_with_cache(
            failing_func,
            messages=[{"role": "user", "content": "test"}],
            context=context
        )
    assert "API Error" in str(exc_info.value)

# 将类定义移到模块级别
@dataclass
class ComplexObject:
    """用于测试的复杂对象"""
    value: str
    data: Dict[str, str]

@dataclass
class Choice:
    """OpenAI API 响应中的选择对象"""
    message: Dict[str, str]
    finish_reason: str

@dataclass
class ChatCompletion:
    """模拟 OpenAI 响应对象"""
    choices: List[Choice]
    model: str
    usage: Dict[str, int]
    
    def __init__(self):
        self.choices = [
            Choice(
                message={
                    "content": "Test response",
                    "role": "assistant"
                },
                finish_reason="stop"
            )
        ]
        self.model = "gpt-4"
        self.usage = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    
    def __eq__(self, other):
        if not isinstance(other, ChatCompletion):
            return False
        return (self.choices[0].message == other.choices[0].message and
                self.model == other.model and
                self.usage == other.usage)

def test_general_object_cache():
    """测试缓存任意对象"""
    def complex_func(*args, **kwargs):
        return ComplexObject("test_value", {"test": "data"})
    
    complex_func.__name__ = 'complex_func'
    complex_func.__module__ = 'test_module'
    
    context = CallContext(context={
        "env": "test",
        "config": {"key": "value"}
    })
    
    # 第一次调用
    result1 = call_with_cache(
        complex_func,
        context=context
    )
    
    # 第二次调用应该返回缓存结果
    result2 = call_with_cache(
        complex_func,
        context=context
    )
    
    assert isinstance(result1, ComplexObject)
    assert isinstance(result2, ComplexObject)
    assert result1.value == result2.value
    assert result1.data == result2.data

def test_openai_object_cache():
    """测试缓存 OpenAI 响应对象"""
    def mock_create(*args, **kwargs):
        return ChatCompletion()
    
    mock_create.__name__ = 'create'
    mock_create.__module__ = 'openai.resources.chat.completions'
    
    context = CallContext(context={
        "api_key": "test_key",
        "base_url": "https://api.test.com",
        "provider": "OPENAI"
    })
    
    # 第一次调用
    result1 = call_with_cache(
        mock_create,
        messages=[{"role": "user", "content": "test"}],
        context=context
    )
    
    # 第二次调用应该返回缓存结果
    result2 = call_with_cache(
        mock_create,
        messages=[{"role": "user", "content": "test"}],
        context=context
    )
    
    assert isinstance(result1, ChatCompletion)
    assert isinstance(result2, ChatCompletion)
    assert result1.choices[0].message['content'] == result2.choices[0].message['content']
    assert result1.usage == result2.usage

@pytest.mark.asyncio
async def test_error_caching():
    """测试错误缓存"""
    def failing_func(*args, **kwargs):
        raise Exception("API Error")
    
    failing_func.__name__ = 'failing_func'
    failing_func.__module__ = 'test_module'
    
    context = CallContext(context={
        "test": "error_case"
    })
    
    with pytest.raises(RuntimeError) as exc_info:
        call_with_cache(
            failing_func,
            messages=[{"role": "user", "content": "test"}],
            context=context
        )
    assert "API Error" in str(exc_info.value)
    
    with pytest.raises(RuntimeError) as exc_info:
        call_with_cache(
            failing_func,
            messages=[{"role": "user", "content": "test"}],
            context=context
        )
    assert "API Error" in str(exc_info.value)

def test_iterator_cache():
    """测试迭代器缓存"""
    def iter_func():
        return iter([1, 2, 3, 4, 5])
    
    iter_func.__name__ = 'iter_func'
    iter_func.__module__ = 'test_module'
    
    context = CallContext(context={"test": "iterator"})
    
    # 第一次调用
    result1 = call_with_cache(iter_func, context=context)
    items1 = list(result1)
    
    # 第二次调用
    result2 = call_with_cache(iter_func, context=context)
    items2 = list(result2)
    
    assert items1 == items2 == [1, 2, 3, 4, 5]
