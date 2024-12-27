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


class TestTagIndexing:
    """测试标签索引功能"""
    
    @pytest.fixture
    def tag_storage_factory(self, tmp_path):
        def create_storage():
            return JiaoziCache.create_with_json_storage(
                data_dir=str(tmp_path),
                filename="tag_test.json",
                data_class=PydanticComplexData,
                indexes=["tags"],  # 启用标签索引
                cache_size=1000
            )
        return create_storage

    def test_tag_indexing_basic(self, tag_storage_factory):
        """测试基本的标签索引功能"""
        storage = tag_storage_factory()
        
        # 创建测试数据
        data1 = PydanticComplexData(
            id="1",
            tags=["python", "web"]
        )
        data2 = PydanticComplexData(
            id="2",
            tags=["python", "api"]
        )
        
        storage.set(data1, "owner1")
        storage.set(data2, "owner2")
        
        # 验证索引结构 - 通过 _index 访问
        assert storage._index is not None
        assert "tags" in storage._index.indexes
        assert "python" in storage._index.indexes["tags"]
        assert set(storage._index.indexes["tags"]["python"]) == {"owner1", "owner2"}
        assert "web" in storage._index.indexes["tags"]
        assert storage._index.indexes["tags"]["web"] == ["owner1"]

    def test_tag_index_update(self, tag_storage_factory):
        """测试标签索引更新"""
        storage = tag_storage_factory()
        
        # 初始数据
        data = PydanticComplexData(
            id="1",
            tags=["python", "web"]
        )
        storage.set(data, "owner1")
        
        # 验证初始索引
        assert "python" in storage._index.indexes["tags"]
        assert storage._index.indexes["tags"]["python"] == ["owner1"]
        
        # 更新标签
        updated_data = PydanticComplexData(
            id="1",
            tags=["python", "api"]  # 移除 'web'，添加 'api'
        )
        storage.set(updated_data, "owner1")
        
        # 验证索引更新
        assert "web" not in storage._index.indexes["tags"]
        assert "api" in storage._index.indexes["tags"]
        assert storage._index.indexes["tags"]["python"] == ["owner1"]
        assert storage._index.indexes["tags"]["api"] == ["owner1"]

    def test_tag_deletion(self, tag_storage_factory):
        """测试删除带标签的数据"""
        storage = tag_storage_factory()
        
        # 创建测试数据
        data = PydanticComplexData(
            id="1",
            tags=["python", "web"]
        )
        storage.set(data, "owner1")
        
        # 验证初始索引
        assert "python" in storage._index.indexes["tags"]
        assert "web" in storage._index.indexes["tags"]
        
        # 删除数据
        storage.delete("owner1")
        
        # 验证索引已清理
        assert "owner1" not in storage._index.indexes["tags"].get("python", [])
        assert "owner1" not in storage._index.indexes["tags"].get("web", [])

    def test_tag_index_persistence(self, tag_storage_factory, tmp_path):
        """测试标签索引的持久化"""
        storage = tag_storage_factory()
        
        # 创建测试数据
        data = PydanticComplexData(
            id="1",
            tags=["python", "web"]
        )
        storage.set(data, "owner1")
        
        # 验证索引文件
        index_file = tmp_path / ".indexes" / "tag_test.json"
        assert index_file.exists()
        
        # 读取并验证索引内容
        with open(index_file, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
            assert "tags" in index_data
            assert "python" in index_data["tags"]
            assert "web" in index_data["tags"]
            assert index_data["tags"]["python"] == ["owner1"]

    def test_tag_index_load(self, tag_storage_factory):
        """测试标签索引的加载"""
        # 创建第一个存储实例并设置数据
        storage1 = tag_storage_factory()
        data = PydanticComplexData(
            id="1",
            tags=["python", "web"]
        )
        storage1.set(data, "owner1")
        
        # 创建新的存储实例
        storage2 = tag_storage_factory()
        
        # 验证索引是否正确加载
        assert "tags" in storage2._index.indexes
        assert "python" in storage2._index.indexes["tags"]
        assert "web" in storage2._index.indexes["tags"]
        assert storage2._index.indexes["tags"]["python"] == ["owner1"]
        
        # 验证使用加载的索引进行查询
        with patch.object(storage2, '_find_with_index') as mock_index_find:
            mock_index_find.return_value = ["owner1"]
            results = storage2.find({"tags": "python"})
            mock_index_find.assert_called_once_with("tags", "python")
            assert len(results) == 1