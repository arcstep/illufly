"""B树索引后端

本测试模块验证 BTreeIndexBackend 的所有核心功能和特性。
BTreeIndexBackend 是一个基于 B 树的索引实现，支持多字段索引、复杂查询操作和持久化存储。

一、使用示例:

1. 基础索引操作:

```python
from illufly.io.jiaozi_cache.index import BTreeIndexBackend

# 创建索引实例
index = BTreeIndexBackend(
    data_dir="data",
    filename="users.idx",
    index_fields=["name", "age", "created_at", "tags"]
)

# 添加文档
doc1 = {
    "name": "Alice",
    "age": 25,
    "created_at": datetime(2024, 1, 1),
    "tags": ["user", "active"]
}
index.update_index(doc1, "user1")

# 精确查询
results = index.find_with_index("name", "Alice") # ["user1"]
results = index.find_with_index("age", 25) # ["user1"]
```

2. 高级查询操作:

```python
# 比较查询
## 查找成年用户
active_users = index.query("age", ">=", 18)
## 查找2024年注册的用户
recent_users = index.query("created_at", ">=", datetime(2024, 1, 1))

# 范围查询
## 20-30岁的用户
age_range = index.query("age", "[]", 20, 30)

## 2024年注册的用户
date_range = index.query(
    "created_at", "[]",
    datetime(2024, 1, 1),
    datetime(2024, 12, 31)
)
```

3. 复杂数据类型:

```python
# 日期时间索引
event = {
    "title": "Meeting",
    "scheduled_at": datetime(2024, 3, 15, 14, 30),
    "created_at": datetime.now()
}
index.update_index(event, "event1")

# 嵌套字段索引
user_profile = {
    "name": "Bob",
    "stats": {
        "posts": 100,
        "followers": 500
    },
    "settings": {
        "theme": "dark",
        "language": "en"
    }
}
index.update_index(user_profile, "user2")
```

4. 批量操作和重建:

```python
# 批量添加数据
users = [
    ("user1", {"name": "Alice", "age": 25}),
    ("user2", {"name": "Bob", "age": 30}),
    ("user3", {"name": "Charlie", "age": 35})
]
def data_iterator():
    return users

# 重建索引
index.rebuild_indexes(data_iterator)

5. 删除和更新:

```python
# 删除索引
index.remove_from_index("user1")

# 更新文档
updated_doc = {
    "name": "Alice Smith",
    "age": 26,
    "created_at": datetime(2024, 1, 1)
}
index.update_index(updated_doc, "user1") # 自动处理更新
```

6. 持久化操作:

```python
# 索引会自动保存到指定目录
index = BTreeIndexBackend(
    data_dir="data",
    filename="users.idx",
    index_fields=["name", "age"]
)

# 索引文件位置:
# data/.indexes/users.idx.name.btree
# data/.indexes/users.idx.age.btree
```

二、核心特性:
1. 多字段索引
    - 支持同时索引多个字段
    - 自动识别和记录字段类型
    - 支持嵌套字段路径

2. 查询能力
    - 精确查询: ==
    - 比较查询: >, >=, <, <=
    - 范围查询: [], (), [), (]
    - 支持各种数据类型

3. 数据类型支持
    - 基础类型: int, float, str, bool
    - 日期时间: datetime
    - 序列化和反序列化
    - 类型安全的查询

三、注意事项:
1. 字段类型一致性
    - 同一字段应保持类型一致
    - 自动进行类型转换
    - 特殊值(None)不建立索引

2. 性能考虑
    - 合理选择索引字段
    - 批量操作使用重建
    - 定期维护索引

3. 持久化
    - 确保目录可写
    - 定期备份索引文件
    - 处理文件操作异常
"""

import pytest
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from illufly.io.jiaozi_cache.index.btree_index_backend import BTreeIndexBackend
import logging

@pytest.fixture
def btree_backend(tmp_path):
    """创建测试用的 B 树索引后端实例"""
    logger = logging.getLogger("test_btree")
    logger.setLevel(logging.DEBUG)
    
    # 指定字段类型
    field_types = {
        "name": str,
        "age": int,
        "created_at": datetime,
        "tags": str,  # 列表元素类型
        "nested.field": str
    }
    
    return BTreeIndexBackend(
        data_dir=str(tmp_path),
        filename="test_btree",
        index_fields=["name", "age", "created_at", "tags", "nested.field"],
        field_types=field_types,
        logger=logger
    )

class TestBasicOperations:
    """基本操作测试"""
    
    def test_single_field_index(self, btree_backend):
        """测试单字段索引的基本操作
        
        验证:
        1. 添加索引
        2. 查询索引
        3. 更新索引
        4. 删除索引
        """
        # 添加数据
        data1 = {"name": "test1", "age": 25}
        data2 = {"name": "test2", "age": 30}
        
        btree_backend.update_index(data1, "doc1")
        btree_backend.update_index(data2, "doc2")
        
        # 验证查询
        assert btree_backend.find_with_index("name", "test1") == ["doc1"]
        assert btree_backend.find_with_index("age", 30) == ["doc2"]
        
        # 验证更新
        data1_updated = {"name": "test1_updated", "age": 26}
        btree_backend.update_index(data1_updated, "doc1")
        assert btree_backend.find_with_index("name", "test1") == []
        assert btree_backend.find_with_index("name", "test1_updated") == ["doc1"]
        
        # 验证删除
        btree_backend.remove_from_index("doc1")
        assert btree_backend.find_with_index("name", "test1_updated") == []
        assert btree_backend.find_with_index("age", 26) == []

class TestQueryOperations:
    """查询操作测试"""
    
    def test_comparison_queries(self, btree_backend):
        """测试比较查询操作
        
        验证所有比较操作符:
        ==, !=, >, >=, <, <=
        """
        # 准备测试数据
        data = [
            ({"age": 20}, "doc1"),
            ({"age": 25}, "doc2"),
            ({"age": 30}, "doc3"),
        ]
        
        for item, doc_id in data:
            btree_backend.update_index(item, doc_id)
        
        # 测试各种比较操作
        assert btree_backend.query("age", "==", 25) == ["doc2"]
        assert set(btree_backend.query("age", ">", 25)) == {"doc3"}
        assert set(btree_backend.query("age", ">=", 25)) == {"doc2", "doc3"}
        assert set(btree_backend.query("age", "<", 25)) == {"doc1"}
        assert set(btree_backend.query("age", "<=", 25)) == {"doc1", "doc2"}
    
    def test_range_queries(self, btree_backend):
        """测试范围查询操作
        
        验证所有范围操作符:
        [], (), [), (]
        """
        # 准备测试数据
        data = [
            ({"age": 20}, "doc1"),
            ({"age": 25}, "doc2"),
            ({"age": 30}, "doc3"),
        ]
        
        for item, doc_id in data:
            btree_backend.update_index(item, doc_id)
        
        # 测试各种范围查询
        assert set(btree_backend.query("age", "[]", 20, 30)) == {"doc1", "doc2", "doc3"}
        assert set(btree_backend.query("age", "()", 20, 30)) == {"doc2"}
        assert set(btree_backend.query("age", "[)", 20, 30)) == {"doc1", "doc2"}
        assert set(btree_backend.query("age", "(]", 20, 30)) == {"doc2", "doc3"}

class TestDataTypes:
    """数据类型支持测试"""
    
    def test_datetime_handling(self, btree_backend):
        """测试日期时间类型的处理"""
        dt1 = datetime(2024, 1, 1)
        dt2 = datetime(2024, 1, 2)
        
        # 添加数据
        btree_backend.update_index({"created_at": dt1}, "doc1")
        btree_backend.update_index({"created_at": dt2}, "doc2")
        
        # 验证查询
        assert btree_backend.find_with_index("created_at", dt1) == ["doc1"]
        assert set(btree_backend.query("created_at", "[]", dt1, dt2)) == {"doc1", "doc2"}
    
    def test_nested_fields(self, btree_backend):
        """测试嵌套字段的处理"""
        data = {
            "nested": {
                "field": "test_value"
            }
        }
        
        btree_backend.update_index(data, "doc1")
        assert btree_backend.find_with_index("nested.field", "test_value") == ["doc1"]

class TestPersistence:
    """持久化功能测试"""
    
    def test_save_and_load(self, btree_backend, tmp_path):
        """测试索引的保存和加载"""
        # 添加测试数据
        data = {
            "name": "test",
            "age": 25,
            "created_at": datetime(2024, 1, 1)
        }
        btree_backend.update_index(data, "doc1")
        
        # 保存索引
        btree_backend._save_indexes()
        
        # 创建新实例加载索引
        new_backend = BTreeIndexBackend(
            data_dir=str(tmp_path),
            filename="test_btree",
            index_fields=["name", "age", "created_at"]
        )
        
        # 验证加载的数据
        assert new_backend.find_with_index("name", "test") == ["doc1"]
        assert new_backend.find_with_index("age", 25) == ["doc1"]
        assert new_backend.find_with_index("created_at", datetime(2024, 1, 1)) == ["doc1"]

class TestEdgeCases:
    """边界情况测试"""
    
    def test_special_values(self, btree_backend):
        """测试特殊值的处理"""
        data = [
            ({"name": None}, "doc1"),
            ({"name": ""}, "doc2"),
            ({"other_field": "test"}, "doc3")
        ]
        
        for item, doc_id in data:
            btree_backend.update_index(item, doc_id)
            
        assert btree_backend.find_with_index("name", None) == []
        assert btree_backend.find_with_index("name", "") == ["doc2"]
        assert btree_backend.find_with_index("other_field", "test") == []
    
    def test_type_conversion(self, btree_backend):
        """测试类型转换"""
        # 测试数字类型转换
        btree_backend.update_index({"age": "25"}, "doc1")  # 字符串数字
        btree_backend.update_index({"age": 25.0}, "doc2")  # 浮点数
        
        assert set(btree_backend.find_with_index("age", 25)) == {"doc1", "doc2"}

class TestPerformance:
    """性能测试"""
    
    def test_large_dataset(self, btree_backend):
        """测试大数据集性能"""
        # 生成测试数据
        n = 1000
        data = [({"age": i}, f"doc{i}") for i in range(n)]
        
        # 测试批量插入
        for item, doc_id in data:
            btree_backend.update_index(item, doc_id)
            
        # 验证查询结果
        result = btree_backend.query("age", "[]", n//4, n//2)
        assert len(result) == n//2 - n//4 + 1