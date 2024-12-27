from dataclasses import dataclass
from typing import Callable
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from typing import Dict, Any

import pytest
import logging
import json
from unittest.mock import patch

from illufly.io import JiaoziCache
from pydantic import BaseModel, Field
from illufly.io.jiaozi_cache.backend import JSONFileStorageBackend
from illufly.io.jiaozi_cache.index import HashIndexBackend


class TestFileConfigStoreIndexing:
    @pytest.fixture
    def indexed_storage_factory(self, tmp_path):
        """创建带索引的存储实例"""
        def create_storage(indexes=None, cache_size=1000):
            return JiaoziCache(
                data_dir=str(tmp_path),
                filename="indexed_test.json",
                data_class=StorageData,
                indexes=indexes or [],
                cache_size=cache_size
            )
        return create_storage

    def test_find_auto_uses_index(self, indexed_storage_factory):
        """测试find方法自动使用索引"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 存储测试数据
        for i in range(5):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage.set(data, f"owner{i}")
        
        # 使用索引字段查询时应该走索引
        with patch.object(storage, '_find_with_index') as mock_index_find:
            mock_index_find.return_value = ["owner2"]
            results = storage.find({"email": "user2@test.com"})
            
            # 验证确实调用了索引查询
            mock_index_find.assert_called_once_with("email", "user2@test.com")
            assert len(results) == 1
            assert results[0].id == "2"
        
        # 使用非索引字段时不应该走索引
        with patch.object(storage, '_find_with_index') as mock_index_find:
            results = storage.find({"name": "user3"})
            mock_index_find.assert_not_called()
            assert len(results) == 1
            assert results[0].id == "3"

    def test_multiple_conditions_with_index(self, indexed_storage_factory):
        """测试多条件查询（包含索引和非索引字段）"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 存储测试数据
        data1 = StorageData(id="1", name="张三", email="zhangsan@test.com", age=25)
        data2 = StorageData(id="2", name="张三", email="zhangsan2@test.com", age=30)
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 组合索引和非索引字段查询
        results = storage.find({
            "email": "zhangsan@test.com",  # 索引字段
            "age": 25  # 非索引字段
        })
        assert len(results) == 1
        assert results[0].id == "1"

    def test_index_performance(self, indexed_storage_factory):
        """测试索引性能提升"""
        storage_with_index = indexed_storage_factory(indexes=["email"], cache_size=0)
        storage_without_index = indexed_storage_factory(cache_size=0)
        
        # 存储大量测试数据
        for i in range(100):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage_with_index.set(data, f"owner{i}")
            storage_without_index.set(data, f"owner{i}")
        
        # 测试查询性能
        import time
        
        start_time = time.time()
        results_with_index = storage_with_index.find({"email": "user99@test.com"})
        index_time = time.time() - start_time
        
        start_time = time.time()
        results_without_index = storage_without_index.find({"email": "user99@test.com"})
        no_index_time = time.time() - start_time
        
        # 验证结果正确性和性能提升
        assert len(results_with_index) == len(results_without_index) == 1
        assert results_with_index[0].id == "99"
        assert index_time < no_index_time

    def test_index_structure(self, indexed_storage_factory):
        """测试索引结构的正确性"""
        storage = indexed_storage_factory(indexes=["email", "name"])
        
        # 存储测试数据
        data1 = StorageData(id="1", name="张三", email="zhangsan@test.com")
        data2 = StorageData(id="2", name="张三", email="zhangsan2@test.com")
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 验证索引结构
        assert storage._indexes["email"] == {
            "zhangsan@test.com": ["owner1"],
            "zhangsan2@test.com": ["owner2"]
        }
        assert storage._indexes["name"] == {
            "张三": ["owner1", "owner2"]
        }

    def test_index_update_internal(self, indexed_storage_factory):
        """测试索引更新的内部逻辑"""
        storage = indexed_storage_factory(indexes=["email"])
        
        # 添加初始数据
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 验证初始索引
        assert storage._indexes["email"]["zhangsan@test.com"] == ["owner1"]
        
        # 更新数据
        updated_data = StorageData(id="1", name="张三", email="zhangsan_new@test.com")
        storage.set(updated_data, "owner1")
        
        # 验证索引更新
        assert "zhangsan@test.com" not in storage._indexes["email"]
        assert storage._indexes["email"]["zhangsan_new@test.com"] == ["owner1"]

    def test_delete_with_index(self, indexed_storage_factory):
        """测试删除时索引自动更新"""
        storage = indexed_storage_factory(indexes=["email"])
        
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 删除数据并验证索引更新
        storage.delete("owner1")
        assert "zhangsan@test.com" not in storage._indexes["email"]
        assert storage.find({"email": "zhangsan@test.com"}) == []

    def test_index_persistence_format(self, indexed_storage_factory, tmp_path):
        """测试索引持久化格式"""
        storage = indexed_storage_factory(indexes=["email"])
        
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage.set(data, "owner1")
        
        # 验证索引文件
        index_file = tmp_path / ".indexes" / "indexed_test.json"
        assert index_file.exists()
        
        with open(index_file, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            assert "email" in index_data
            assert index_data["email"]["zhangsan@test.com"] == ["owner1"]

    def test_index_load_on_init(self, indexed_storage_factory, tmp_path):
        """测试初始化时加载索引"""
        # 第一个实例创建索引
        storage1 = indexed_storage_factory(indexes=["email"])
        data = StorageData(id="1", name="张三", email="zhangsan@test.com")
        storage1.set(data, "owner1")
        
        # 创建新实例并验证索引加载
        storage2 = indexed_storage_factory(indexes=["email"])
        assert "email" in storage2._indexes
        assert storage2._indexes["email"]["zhangsan@test.com"] == ["owner1"]
        
        # 验证索引可用
        results = storage2.find({"email": "zhangsan@test.com"})
        assert len(results) == 1
        assert results[0].id == "1"

    def test_invalid_index_field(self, indexed_storage_factory):
        """测试无效索引字段处理"""
        with pytest.raises(ValueError) as exc_info:
            storage = indexed_storage_factory(indexes=["non_existent_field"])
        assert "无效的索引字段" in str(exc_info.value)
