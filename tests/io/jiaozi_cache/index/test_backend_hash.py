"""哈希索引测试套件

本测试模块验证 HashIndexBackend 的所有核心功能和特性。
HashIndexBackend 是一个基于哈希表的索引实现，提供类型安全的精确匹配查询。

核心特性:
1. 类型安全
    - 字段类型声明: 通过 field_types 定义每个字段的类型
    - 类型验证: 在索引更新前验证所有值的类型
    - 类型转换: 支持自动和强制类型转换
    - 列表元素: 确保列表中每个元素符合字段类型

2. 错误处理策略
    - STRICT: 任何类型不匹配都会抛出异常，并回滚整个操作
    - WARNING: 记录警告并跳过无效值，保留有效值
    - COERCE: 尝试更宽松的类型转换，如 "25.5" -> 25

3. 事务一致性
    - 原子性: 更新要么完全成功，要么完全失败
    - 回滚: 错误发生时自动回滚所有更改
    - 持久化: 确保磁盘状态与内存一致

4. 数据管理
    - 类型持久化: 保存和加载字段类型信息
    - 增量更新: 自动处理同一 owner_id 的新值
    - 空间优化: 自动清理无效索引
    - 批量操作: 支持列表值的批量索引

使用示例:

```python
# 创建类型安全的索引
index = HashIndexBackend(
    field_types={
        "name": str,
        "age": int,
        "tags": str # 用于列表值
    },
    error_handling=ErrorHandling.STRICT
)

# 添加带类型验证的数据
index.update_index({
    "name": "test",
    "age": 25,
    "tags": ["python", "coding"]
}, "doc1")

# 类型错误会被拒绝
try:
    index.update_index({
        "name": "test",
        "age": "not_a_number"
    }, "doc2")
except TypeMismatchError:
    print("类型错误，整个操作被回滚")
```
"""

import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from illufly.io.jiaozi_cache.index import (
    HashIndexBackend, 
    ErrorHandling,
    TypeMismatchError
)
import logging

@pytest.fixture
def typed_index(tmp_path):
    """创建一个类型安全的索引实例"""
    # 配置调试日志
    logger = logging.getLogger('test_typed_index')
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return HashIndexBackend(
        data_dir=str(tmp_path),
        filename="typed.idx",
        field_types={
            "name": str,
            "age": int,
            "score": float,
            "tags": str,  # 用于列表值
            "created_at": datetime,
            "active": bool
        },
        error_handling=ErrorHandling.STRICT,
        logger=logger
    )

class TestTypeHandling:
    """类型处理测试"""
    
    def test_basic_type_validation(self, typed_index):
        """测试基本类型验证
        
        验证:
        1. 正确类型的值能被接受
        2. 错误类型的值会被拒绝
        3. 可转换的值会被正确处理
        """
        # 正确类型
        data = {
            "name": "test",
            "age": 25,
            "score": 95.5,
            "active": True
        }
        typed_index.update_index(data, "doc1")
        
        # 验证查询
        assert typed_index.find_with_index("name", "test") == ["doc1"]
        assert typed_index.find_with_index("age", 25) == ["doc1"]
        assert typed_index.find_with_index("score", 95.5) == ["doc1"]
        assert typed_index.find_with_index("active", True) == ["doc1"]
        
        # 错误类型
        with pytest.raises(TypeMismatchError):
            typed_index.update_index({"age": "not_a_number"}, "doc2")

    def test_type_conversion_modes(self, tmp_path):
        """测试不同的类型转换模式"""
        # STRICT 模式
        strict_index = HashIndexBackend(
            data_dir=str(tmp_path),
            filename="strict.idx",
            field_types={"age": int},
            error_handling=ErrorHandling.STRICT
        )
        
        # 这里应该抛出异常
        with pytest.raises(TypeMismatchError):
            strict_index.update_index({"age": "25.5"}, "doc1")
        
        # WARNING 模式
        warning_index = HashIndexBackend(
            data_dir=str(tmp_path),
            filename="warning.idx",
            field_types={"age": int},
            error_handling=ErrorHandling.WARNING
        )
        
        warning_index.update_index({"age": "25.5"}, "doc1")
        assert warning_index.find_with_index("age", 25) == []
        
        # COERCE 模式
        coerce_index = HashIndexBackend(
            data_dir=str(tmp_path),
            filename="coerce.idx",
            field_types={"age": int},
            error_handling=ErrorHandling.COERCE
        )
        
        coerce_index.update_index({"age": "25.5"}, "doc1")
        assert coerce_index.find_with_index("age", 25) == ["doc1"]

    def test_list_type_safety(self, typed_index):
        """测试列表值的类型安全"""
        # 有效的列表值
        typed_index.update_index({"tags": ["python", "test"]}, "doc1")
        assert typed_index.find_with_index("tags", "python") == ["doc1"]

        # 混合类型列表
        with pytest.raises(TypeMismatchError):
            typed_index.update_index({"tags": ["python", 123, True]}, "doc2")  # 包含非字符串值

class TestPersistence:
    """持久化测试"""
    
    def test_type_info_persistence(self, tmp_path):
        """测试类型信息的持久化"""
        # 创建并保存索引
        index1 = HashIndexBackend(
            data_dir=str(tmp_path),
            filename="test.idx",
            field_types={
                "age": int,
                "created_at": datetime
            }
        )
        
        dt = datetime(2024, 1, 1)
        index1.update_index({
            "age": 25,
            "created_at": dt
        }, "doc1")
        
        # 创建新实例加载索引
        index2 = HashIndexBackend(
            data_dir=str(tmp_path),
            filename="test.idx"
        )
        
        # 验证类型信息和数据
        assert index2._field_types["age"] == int
        assert index2._field_types["created_at"] == datetime
        assert index2.find_with_index("age", 25) == ["doc1"]
        assert index2.find_with_index("created_at", dt) == ["doc1"]

def test_error_recovery(typed_index):
    """测试错误恢复"""
    # 成功的更新
    typed_index.update_index({
        "name": "test",
        "age": 25
    }, "doc1")
    
    # 失败的更新应该完全回滚
    with pytest.raises(TypeMismatchError):
        typed_index.update_index({
            "name": "test2",
            "age": "invalid"
        }, "doc2")
    
    # 验证索引状态 - 失败的更新应该被完全回滚
    assert typed_index.find_with_index("name", "test") == ["doc1"]
    assert typed_index.find_with_index("name", "test2") == []  # 不应该有 doc2
    assert typed_index.find_with_index("age", 25) == ["doc1"]

def test_index_fields(typed_index):
    """验证索引字段推导
    
    验证:
    1. 所有类型定义的字段都可以建立索引
    2. 未定义类型的字段不能建立索引
    """
    # 验证已定义类型的字段
    assert typed_index.has_index("name")
    assert typed_index.has_index("age")
    assert typed_index.has_index("score")
    assert typed_index.has_index("tags")
    assert typed_index.has_index("created_at")
    assert typed_index.has_index("active")
    
    # 验证未定义类型的字段
    assert not typed_index.has_index("undefined_field")
