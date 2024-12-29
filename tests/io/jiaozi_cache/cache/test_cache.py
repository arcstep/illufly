from dataclasses import dataclass
from typing import Callable
from datetime import datetime
from typing import List, Optional
import pytest
import logging

from illufly.io import JiaoziCache, IndexType
from tests.io.jiaozi_cache.conftest import StorageData

class TestFileConfigStoreCache:
    """测试FileConfigStore的缓存功能"""
    
    @pytest.fixture
    def cached_storage_factory(self, tmp_path):
        def create_storage(cache_size=10):
            return JiaoziCache.create_with_json_storage(
                data_dir=str(tmp_path),
                filename="cached_test.json",
                data_class=StorageData,
                index_config={},  # 默认不使用索引
                cache_size=cache_size
            )
        return create_storage

    def test_cache_hit(self, cached_storage_factory):
        """测试缓存命中"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 清除缓存，确保第一次需要从文件加载
        storage.clear_cache()
        
        # 第一次获取（从文件加载）
        result1 = storage.get("owner1")
        assert result1.id == "1"
        
        # 验证缓存状态（应该有一次未命中）
        cache_info = storage.get_cache_info()
        assert cache_info["misses"] == 1
        assert cache_info["hits"] == 0
        
        # 第二次获取（从缓存加载）
        result2 = storage.get("owner1")
        assert result2.id == "1"
        
        # 验证缓存命中增加
        cache_info = storage.get_cache_info()
        assert cache_info["hits"] == 1
        assert cache_info["misses"] == 1
        assert cache_info["type"] == "LRU"
        assert cache_info["size"] == 1

    def test_cache_miss(self, cached_storage_factory):
        """测试缓存未命中"""
        storage = cached_storage_factory()
        
        # 尝试获取不存在的数据
        result = storage.get("non_existent")
        assert result is None
        
        # 验证未命中计数
        cache_info = storage.get_cache_info()
        assert cache_info["misses"] == 1
        assert cache_info["hits"] == 0

    def test_cache_eviction(self, cached_storage_factory):
        """测试缓存淘汰"""
        storage = cached_storage_factory(cache_size=2)
        
        # 存储3条数据（超过缓存容量）
        for i in range(3):
            data = StorageData(id=str(i), name=f"test{i}", email=f"test{i}@example.com")
            storage.set(data, f"owner{i}")
        
        # 验证缓存信息
        cache_info = storage.get_cache_info()
        assert cache_info["size"] <= 2  # 缓存大小不超过容量
        assert cache_info["capacity"] == 2
        assert cache_info["type"] == "LRU"

    def test_cache_eviction_with_stats(self, cached_storage_factory):
        """测试缓存淘汰时的统计信息"""
        storage = cached_storage_factory(cache_size=2)
        
        # 存储3条数据（超过缓存容量）
        for i in range(3):
            data = StorageData(id=str(i), name=f"test{i}", email=f"test{i}@example.com")
            storage.set(data, f"owner{i}")
        
        # 访问最早的数据（应该已被淘汰）
        result = storage.get("owner0")
        assert result is not None  # 数据仍能从存储中获取
        
        # 验证缓存状态
        cache_info = storage.get_cache_info()
        assert cache_info["size"] == 2  # 缓存大小不变
        assert cache_info["capacity"] == 2
        assert cache_info["misses"] >= 1  # 至少有一次未命中（访问被淘汰的数据）
        assert cache_info["type"] == "LRU"

    def test_cache_update(self, cached_storage_factory):
        """测试缓存更新"""
        storage = cached_storage_factory()
        
        # 存储初始数据
        data1 = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data1, "owner1")
        
        # 获取一次以确保数据在缓存中
        result1 = storage.get("owner1")
        assert result1.name == "test"
        
        # 更新数据
        data2 = StorageData(id="1", name="updated", email="test@example.com")
        storage.set(data2, "owner1")
        
        # 验证缓存是否更新
        result2 = storage.get("owner1")
        assert result2.name == "updated"
        
        # 验证缓存状态
        cache_info = storage.get_cache_info()
        assert cache_info["size"] == 1
        assert cache_info["type"] == "LRU"

    def test_cache_update_with_stats(self, cached_storage_factory):
        """测试更新操作的缓存统计"""
        storage = cached_storage_factory()
        
        # 存储初始数据
        data1 = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data1, "owner1")
        
        # 第一次获取
        result1 = storage.get("owner1")
        assert result1.name == "test"
        
        # 更新数据
        data2 = StorageData(id="1", name="updated", email="test@example.com")
        storage.set(data2, "owner1")
        
        # 再次获取（应该是缓存命中）
        result2 = storage.get("owner1")
        assert result2.name == "updated"
        
        # 验证缓存统计
        cache_info = storage.get_cache_info()
        assert cache_info["hits"] >= 1  # 至少有一次命中
        assert cache_info["size"] == 1
        assert cache_info["type"] == "LRU"

    def test_cache_clear(self, cached_storage_factory):
        """测试缓存清理"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 第一次获取，加入缓存
        result1 = storage.get("owner1")
        assert result1.name == "test"
        
        # 清除缓存
        storage.clear_cache()
        
        # 验证缓存已清空
        cache_info = storage.get_cache_info()
        assert cache_info["size"] == 0
        assert cache_info["type"] == "LRU"
        
        # 再次获取，验证数据仍然可以访问
        result2 = storage.get("owner1")
        assert result2.name == "test"

    def test_indexed_search_with_cache(self, tmp_path):
        """测试索引搜索与缓存交互"""
        # 创建带索引的存储
        storage = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="cached_test.json",
            data_class=StorageData,
            index_config={"email": IndexType.HASH},  # 启用email索引
            cache_size=5
        )
        
        # 存储测试数据
        for i in range(10):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage.set(data, f"owner{i}")
        
        # 使用索引查询
        results = storage.query({"email": "user5@test.com"})
        assert len(results) == 1
        assert results[0].id == "5"
        
        # 验证缓存状态
        cache_info = storage.get_cache_info()
        assert cache_info["size"] <= cache_info["capacity"]
        assert cache_info["type"] == "LRU"
