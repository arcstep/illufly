from dataclasses import dataclass
from typing import Callable, Dict
from datetime import datetime
import pytest
import logging
import json
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
                cache_size=cache_size
            )
        return create_storage

    def test_basic_query(self, indexed_storage_factory):
        """测试基本查询功能"""
        storage = indexed_storage_factory({
            "email": IndexType.HASH,
            "age": IndexType.BTREE
        })
        
        # 存储测试数据
        for i in range(5):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com",
                age=20 + i
            )
            storage.set(data, f"owner{i}")
        
        # 测试哈希索引等值查询
        results = storage.query({"email": "user2@test.com"})
        assert len(results) == 1
        assert results[0].id == "2"
        
        # 测试B树索引范围查询
        results = storage.query({"age": (">=", 22)})
        assert len(results) == 3
        assert all(r.age >= 22 for r in results)
        
        # 测试非索引字段查询（应该发出警告）
        with pytest.warns(UserWarning):
            results = storage.query({"name": "user3"})
            assert len(results) == 1
            assert results[0].id == "3"

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
        assert "无效的索引字段" in str(exc_info.value)

    def test_rebuild_indexes(self, indexed_storage_factory):
        """测试重建索引"""
        storage = indexed_storage_factory({"email": IndexType.HASH})
        
        data1 = StorageData(id="1", email="test1@example.com")
        data2 = StorageData(id="2", email="test2@example.com")
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 清除并重建索引
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
        results = storage.query({"age": "22"})
        assert len(results) == 1
        assert results[0].id == "2"
        
        # 测试字符串类型的日期查询
        results = storage.query({"created_at": "2024-01-03"})
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
        assert storage._index._btree_backend is not None
        
        # 检查索引内容
        index = storage._index._btree_backend._indexes.get("age")
        assert index is not None
        print("Index content:", index._tree)

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
        
        # 添加测试数据
        data = StorageData(
            id="1", 
            created_at=datetime(2024, 1, 1)
        )
        storage.set(data, "owner1")
        
        # 获取B树索引后端
        btree_backend = storage._index._btree_backend
        assert btree_backend is not None
        
        # 检查索引内容
        index = btree_backend._indexes.get("created_at")
        assert index is not None
        
        # 打印索引内容和序列化结果
        print("DateTime value:", index._tree.keys() if index._tree else None)
        
        # 尝试序列化
        try:
            serialized = index._serialize_tree(index._tree)
            print("Serialized datetime tree:", serialized)
        except Exception as e:
            print("DateTime serialization error:", str(e))
