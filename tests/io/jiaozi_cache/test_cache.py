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

class TestFileConfigStoreCache:
    """测试FileConfigStore的缓存功能"""
    
    @pytest.fixture
    def cached_storage_factory(self, tmp_path):
        def create_storage(cache_size=10):
            return JiaoziCache(
                data_dir=str(tmp_path),
                filename="cached_test.json",
                data_class=StorageData,
                cache_size=cache_size
            )
        return create_storage

    def test_cache_hit(self, cached_storage_factory, tmp_path):
        """测试缓存命中"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 清除缓存，确保第一次需要从文件加载
        storage.clear_cache()
        
        # 记录实际的文件路径
        real_file_path = storage._get_file_path("owner1")
        
        # 第一次获取（从文件加载）
        with patch.object(storage, '_get_file_path') as mock_get_path:
            # 设置mock返回实际的文件路径
            mock_get_path.return_value = real_file_path
            
            result1 = storage.get("owner1")
            assert result1.id == "1"
            mock_get_path.assert_called_once()
        
        # 第二次获取（应该从缓存加载）
        with patch.object(storage, '_get_file_path') as mock_get_path:
            result2 = storage.get("owner1")
            assert result2.id == "1"
            mock_get_path.assert_not_called()

    def test_cache_eviction(self, cached_storage_factory):
        """测试缓存淘汰"""
        storage = cached_storage_factory(cache_size=2)
        
        # 存储3条数据（超过缓存容量）
        for i in range(3):
            data = StorageData(id=str(i), name=f"test{i}", email=f"test{i}@example.com")
            storage.set(data, f"owner{i}")
        
        # 验证缓存信息
        cache_info = storage.get_cache_info()
        assert cache_info["size"] == 2
        assert cache_info["capacity"] == 2

    def test_cache_update(self, cached_storage_factory):
        """测试缓存更新"""
        storage = cached_storage_factory()
        
        # 存储初始数据
        data1 = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data1, "owner1")
        
        # 更新数据
        data2 = StorageData(id="1", name="updated", email="test@example.com")
        storage.set(data2, "owner1")
        
        # 验证缓存是否更新
        result = storage.get("owner1")
        assert result.name == "updated"

    def test_cache_clear(self, cached_storage_factory):
        """测试缓存清理"""
        storage = cached_storage_factory()
        
        # 存储测试数据
        data = StorageData(id="1", name="test", email="test@example.com")
        storage.set(data, "owner1")
        
        # 清除缓存
        storage.clear_cache()
        
        # 验证需要重新从文件加载
        with patch.object(storage, '_get_file_path') as mock_get_path:
            storage.get("owner1")
            mock_get_path.assert_called_once()

    def test_indexed_search_with_cache(self, cached_storage_factory):
        """测试索引搜索与缓存交互"""
        storage = cached_storage_factory(cache_size=5)
        storage._index_fields = ["email"]  # 启用索引
        
        # 存储测试数据
        for i in range(10):
            data = StorageData(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage.set(data, f"owner{i}")
        
        # 使用索引查询
        results = storage.find({"email": "user5@test.com"})
        assert len(results) == 1
        assert results[0].id == "5"
        
        # 验证缓存大小没有超出限制
        cache_info = storage.get_cache_info()
        assert cache_info["size"] <= cache_info["capacity"]
