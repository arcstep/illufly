import pytest
from typing import Dict, Any
from datetime import datetime
from pathlib import Path

from illufly.io.jiaozi_cache import CachedJSONStorage

@pytest.fixture
def storage(tmp_path) -> CachedJSONStorage:
    """创建测试用的存储实例"""
    return CachedJSONStorage[Dict](
        data_dir=str(tmp_path),
        segment="test_index.json",
        cache_size=100,
        flush_threshold=10
    )

class TestCachedJSONStorage:
    """缓存存储测试用例"""
    
    def test_init(self, storage):
        """测试初始化"""
        assert storage is not None
        assert isinstance(storage, CachedJSONStorage)
        
    def test_basic_operations(self, storage):
        """测试基本操作：添加/获取/删除"""
        # 测试数据
        test_data = {"id": "test1", "value": 42}
        
        # 添加
        storage.set("key1", test_data)
        assert storage.get("key1") == test_data
        
        # 更新
        test_data["value"] = 43
        storage.set("key1", test_data)
        assert storage.get("key1")["value"] == 43
        
        # 删除
        storage.delete("key1")  # 使用 delete 而不是 remove
        assert storage.get("key1") is None
        
        # 不存在的键
        assert storage.get("nonexistent") is None
        
    def test_list_keys(self, storage):
        """测试列出所有键"""
        # 添加测试数据
        data = {
            "key1": {"value": 1},
            "key2": {"value": 2},
            "key3": {"value": 3}
        }
        
        for key, value in data.items():
            storage.set(key, value)
            
        # 强制刷新确保数据写入
        storage.flush()
        
        keys = storage.list_keys()
        assert len(keys) == 3
        assert set(keys) == {"key1", "key2", "key3"}
        
    def test_clear(self, storage):
        """测试清空存储"""
        # 添加测试数据
        storage.set("key1", {"value": 1})
        storage.set("key2", {"value": 2})
        
        # 清空
        storage.clear()
        assert len(storage.list_keys()) == 0
        assert storage.get("key1") is None
        
    @pytest.mark.performance
    def test_batch_performance(self, storage):
        """测试批量操作性能"""
        # 生成测试数据
        num_items = 1000
        start_time = datetime.now()
        
        # 批量添加
        for i in range(num_items):
            storage.set(f"key{i}", {"value": i})
            
        duration = (datetime.now() - start_time).total_seconds()
        
        # 验证性能
        assert duration < 5  # 应在5秒内完成
        
        # 强制刷新
        storage.flush()
        
        # 验证数据完整性
        assert len(storage.list_keys()) == num_items
        for i in range(num_items):
            assert storage.get(f"key{i}") == {"value": i}