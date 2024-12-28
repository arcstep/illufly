"""JiaoziCache 查询功能

本模块测试 JiaoziCache 的查询功能，包括：

1. 哈希索引和B树索引的基本操作
2. 范围查询和组合查询
3. 索引持久化和重建
4. 类型转换和错误处理

一、使用示例:

1. 创建带索引的缓存:

```python
cache = JiaoziCache.create_with_json_storage(
    data_dir="data",
    filename="users.json",
    data_class=UserData,
    index_config={
        "email": IndexType.HASH, # 哈希索引适合等值查询
        "age": IndexType.BTREE, # B树索引支持范围查询
        "status": IndexType.HASH
    }
)
```

2. 基本查询:

```python
# 等值查询
results = cache.query({"email": "user@example.com"})

# 范围查询
results = cache.query({"age": ("[]", 20, 30)}) # 闭区间 [20, 30]
results = cache.query({"age": ("()", 20, 30)}) # 开区间 (20, 30)
results = cache.query({"age": (">=", 20)}) # 大于等于

# 组合查询
    results = cache.query({
        "status": "active",
        "age": (">=", 20)
    })
```

3. 便捷查询方法:

```python
# 查找单个记录
user = cache.find_one("email", "user@example.com")

# 通过ID查找
user = cache.find_by_id("user123")

# 查找多个记录
users = cache.find_many("status", ["active", "pending"])
```

4. 日期时间查询:

```python
from datetime import datetime
# 日期范围查询
results = cache.query({
    "created_at": ("[)",
        datetime(2024, 1, 1),
        datetime(2024, 1, 7)
    )
})
```

5. 索引重建:

```python
# 重建所有索引
cache.rebuild_indexes()
```

二、注意事项:
1. 哈希索引仅支持等值查询和集合操作
2. B树索引支持所有比较操作和范围查询
3. 查询条件的数据类型会自动转换为索引字段的类型
4. 索引会自动持久化到磁盘
5. 非索引字段的查询会触发全表扫描
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime
import pytest
import logging
import time
import warnings

from illufly.io import JiaoziCache
from illufly.io.jiaozi_cache.index import IndexType
from tests.io.jiaozi_cache.conftest import StorageData

class TestJiaoziCacheIndexing:
    """测试JiaoziCache的索引功能"""

    @pytest.fixture
    def indexed_storage_factory(self, tmp_path):
        """创建带索引的存储实例"""
        def create_storage(index_config: Dict[str, IndexType] = None, cache_size=1000):
            return JiaoziCache.create_with_json_storage(
                data_dir=str(tmp_path),
                filename="indexed_test.json",
                data_class=StorageData,
                index_config=index_config,
                cache_size=cache_size,
                serializer=lambda x: x.to_dict(),
                deserializer=StorageData.from_dict
            )
        return create_storage

    def test_basic_query(self, indexed_storage_factory):
        """测试基本查询功能"""
        storage = indexed_storage_factory({
            "email": IndexType.HASH,
            "age": IndexType.BTREE
        })
        
        # 检查索引初始化
        assert storage._index is not None
        hash_backend = storage._index._hash_backend
        assert hash_backend is not None
        
        # 打印更详细的索引信息
        print("\nIndex initialization:")
        print(f"- Index backend type: {type(storage._index)}")
        print(f"- Hash backend type: {type(hash_backend)}")
        print(f"- Field types: {hash_backend._field_types}")
        print(f"- Indexed fields: {list(hash_backend._field_types.keys())}")
        
        # 存储测试数据
        for i in range(5):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com",
                age=20 + i
            )
            print(f"\nStoring data {i}:")
            print(f"- Data: {data.to_dict()}")
            
            # 存储数据时会自动更新索引
            storage.set(data, f"owner{i}")
            
            # 打印每次更新后的详细状态
            print(f"After set operation:")
            print(f"- Hash backend fields: {hash_backend._field_types}")
            print(f"- Email index content: {dict(hash_backend._indexes['email'])}")
            
            # 验证每次更新后都能查询到
            results = storage.query({"email": data.email})
            print(f"Query results:")
            print(f"- Query value: {data.email}")
            print(f"- Results: {[r.id for r in results]}")
            print(f"- Raw results: {results}")
            
            # 检查存储的数据
            stored_data = storage.get(f"owner{i}")
            print(f"Stored data check:")
            print(f"- Stored data: {stored_data.to_dict() if stored_data else None}")
        
        # 检查最终索引内容
        print("\nFinal state:")
        print(f"- Field types: {hash_backend._field_types}")
        print(f"- All indexes: {dict(hash_backend._indexes)}")
        
        # 测试哈希索引等值查询
        target_email = "user2@test.com"
        print(f"\nFinal query:")
        print(f"- Target email: {target_email}")
        results = storage.query({"email": target_email})
        print(f"- Query results: {[r.id for r in results]}")
        print(f"- Raw results: {results}")
        
        assert len(results) == 1
        assert results[0].id == "2"

    def test_range_queries(self, indexed_storage_factory):
        """测试范围查询功能"""
        storage = indexed_storage_factory({
            "age": IndexType.BTREE,
            "created_at": IndexType.BTREE
        })
        
        # 存储测试数据
        for i in range(10):
            data = StorageData(
                id=str(i),
                age=20 + i,
                created_at=datetime(2024, 1, i + 1)
            )
            storage.set(data, f"owner{i}")
        
        # 测试不同类型的范围查询
        results = storage.query({"age": ("[]", 22, 25)})  # 闭区间
        assert len(results) == 4
        assert all(22 <= r.age <= 25 for r in results)
        
        results = storage.query({"age": ("()", 22, 25)})  # 开区间
        assert len(results) == 2
        assert all(22 < r.age < 25 for r in results)
        
        # 测试日期范围查询
        results = storage.query({
            "created_at": ("[)", datetime(2024, 1, 3), datetime(2024, 1, 6))
        })
        assert len(results) == 3
        assert all(datetime(2024, 1, 3) <= r.created_at < datetime(2024, 1, 6) for r in results)

    def test_combined_queries(self, indexed_storage_factory):
        """测试组合查询"""
        storage = indexed_storage_factory({
            "email": IndexType.HASH,
            "age": IndexType.BTREE,
            "status": IndexType.HASH
        })
        
        # 存储测试数据
        data1 = StorageData(
            id="1", email="test1@example.com", 
            age=25, status="active"
        )
        data2 = StorageData(
            id="2", email="test2@example.com", 
            age=30, status="active"
        )
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 测试组合查询
        results = storage.query({
            "status": "active",
            "age": (">=", 28)
        })
        assert len(results) == 1
        assert results[0].id == "2"

    def test_convenience_methods(self, indexed_storage_factory):
        """测试便捷查询方法"""
        storage = indexed_storage_factory({
            "email": IndexType.HASH,
            "status": IndexType.HASH
        })
        
        # 存储测试数据
        data1 = StorageData(id="1", email="test1@example.com", status="active")
        data2 = StorageData(id="2", email="test2@example.com", status="active")
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 测试 find_one
        result = storage.find_one("email", "test1@example.com")
        assert result.id == "1"
        
        # 测试 find_by_id
        result = storage.find_by_id("owner2")
        assert result.id == "2"
        
        # 测试 find_many
        results = storage.find_many("status", ["active"])
        assert len(results) == 2

    def test_index_performance(self, indexed_storage_factory):
        """测试索引性能提升"""
        storage_with_index = indexed_storage_factory(
            {"email": IndexType.HASH}, 
            cache_size=0
        )
        storage_without_index = indexed_storage_factory(cache_size=0)
        
        # 存储大量测试数据
        for i in range(100):
            data = StorageData(id=str(i), email=f"user{i}@test.com")
            storage_with_index.set(data, f"owner{i}")
            storage_without_index.set(data, f"owner{i}")
        
        # 测试查询性能
        start_time = time.time()
        results_with_index = storage_with_index.query({"email": "user99@test.com"})
        index_time = time.time() - start_time
        
        start_time = time.time()
        with pytest.warns(UserWarning):
            results_without_index = storage_without_index.query(
                {"email": "user99@test.com"}
            )
        no_index_time = time.time() - start_time
        
        assert len(results_with_index) == len(results_without_index) == 1
        assert results_with_index[0].id == "99"
        assert index_time < no_index_time

    def test_index_updates(self, indexed_storage_factory):
        """测试索引更新"""
        storage = indexed_storage_factory({"email": IndexType.HASH})
        
        # 添加和更新数据
        data = StorageData(id="1", email="old@test.com")
        storage.set(data, "owner1")
        
        updated_data = StorageData(id="1", email="new@test.com")
        storage.set(updated_data, "owner1")
        
        assert not storage.query({"email": "old@test.com"})
        results = storage.query({"email": "new@test.com"})
        assert len(results) == 1

    def test_index_persistence(self, indexed_storage_factory):
        """测试索引持久化"""
        index_config = {"email": IndexType.HASH}
        
        # 第一个实例
        storage1 = indexed_storage_factory(index_config)
        data = StorageData(id="1", email="test@example.com")
        storage1.set(data, "owner1")
        
        # 第二个实例
        storage2 = indexed_storage_factory(index_config)
        results = storage2.query({"email": "test@example.com"})
        assert len(results) == 1

    def test_invalid_index_field(self, indexed_storage_factory):
        """测试无效索引字段处理"""
        with pytest.raises(ValueError) as exc_info:
            storage = indexed_storage_factory({
                "non_existent_field": IndexType.HASH
            })
        assert "无法获取字段" in str(exc_info.value)

    def test_rebuild_indexes(self, indexed_storage_factory):
        """测试重建索引"""
        storage = indexed_storage_factory({"email": IndexType.HASH})
        
        data1 = StorageData(id="1", email="test1@example.com")
        data2 = StorageData(id="2", email="test2@example.com")
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 除并重建索引
        storage._index.clear()
        storage.rebuild_indexes()
        
        results = storage.query({"email": "test1@example.com"})
        assert len(results) == 1
        assert results[0].id == "1"

    def test_type_mismatch_handling(self, indexed_storage_factory):
        """测试条件中数据类型与索引中类型不同的场景"""
        storage = indexed_storage_factory({
            "age": IndexType.BTREE,
            "created_at": IndexType.BTREE
        })
        
        # 存储测试数据
        for i in range(5):
            data = StorageData(
                id=str(i),
                age=20 + i,
                created_at=datetime(2024, 1, i + 1)
            )
            storage.set(data, f"owner{i}")
        
        # 测试字符串类型的年龄查询
        results = storage.query({"age": ("==", "22")})
        assert len(results) == 1
        assert results[0].id == "2"
        
        # 测试字符串类型的日期查询
        results = storage.query({"created_at": ("==", "2024-01-03")})
        assert len(results) == 1
        assert results[0].id == "2"

    def test_index_creation(self, indexed_storage_factory):
        """测试索引创建"""
        storage = indexed_storage_factory({
            "age": IndexType.BTREE
        })
        
        # 添加测试数据
        data = StorageData(id="1", age=25)
        storage.set(data, "owner1")
        
        # 检查B树索引后端
        btree_backend = storage._index._btree_backend
        assert btree_backend is not None
        
        # 检查索引内容
        index = btree_backend._indexes.get("age")
        assert index is not None
        
        # 检查索引内容 - 使用正确的API
        assert len(index.search(25)) > 0  # 使用 search 方法而不是直接访问内部结构

    def test_btree_index_save(self, indexed_storage_factory):
        """测试B树索引的保存"""
        storage = indexed_storage_factory({
            "age": IndexType.BTREE
        })
        
        # 添加测试数据
        data = StorageData(id="1", age=25)
        storage.set(data, "owner1")
        
        # 获取B树索引后端
        btree_backend = storage._index._btree_backend
        assert btree_backend is not None
        
        # 检查索引内容
        index = btree_backend._indexes.get("age")
        assert index is not None
        
        # 打印索引内容
        print("Index tree:", index._tree)
        
        # 尝试序列化
        try:
            serialized = index._serialize_tree(index._tree)
            print("Serialized tree:", serialized)
        except Exception as e:
            print("Serialization error:", str(e))

    def test_datetime_index_save(self, indexed_storage_factory):
        """测试日期时间索引的保存"""
        storage = indexed_storage_factory({
            "created_at": IndexType.BTREE
        })
        
        test_date = datetime(2024, 1, 1)
        data = StorageData(
            id="1",
            created_at=test_date
        )
        storage.set(data, "owner1")
        
        # 获取B树索引后端
        btree_backend = storage._index._btree_backend
        assert btree_backend is not None
        
        # 检查索引内容
        index = btree_backend._indexes.get("created_at")
        assert index is not None
        
        # 使用正确的API检查索引内容
        results = index.search(test_date.isoformat())
        print("DateTime search results:", results)
        assert len(results) > 0
