import pytest
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from illufly.io.jiaozi_cache import CachedJSONStorage, Indexable

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
    """哈希索引测试用例"""
    
    def test_init(self, storage):
        """测试初始化"""
        assert storage is not None
        assert isinstance(storage, CachedJSONStorage)
        
    def test_basic_operations(self, storage):
        """测试基本操作：添加/获取/删除"""
        # 测试数据
        test_data = {"id": "test1", "value": 42}
        
        # 添加
        storage.add("key1", test_data)
        assert storage.get("key1") == test_data
        
        # 更新
        test_data["value"] = 43
        storage.add("key1", test_data)
        assert storage.get("key1")["value"] == 43
        
        # 删除
        storage.remove("key1")
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
            storage.add(key, value)
            
        keys = storage.list_keys()
        assert len(keys) == 3
        assert set(keys) == {"key1", "key2", "key3"}
        
    def test_clear(self, storage):
        """测试清空索引"""
        # 添加测试数据
        storage.add("key1", {"value": 1})
        storage.add("key2", {"value": 2})
        
        # 清空
        storage.clear()
        assert len(storage.list_keys()) == 0
        assert storage.get("key1") is None
        
    def test_storage_integration(self, storage, tmp_path):
        """测试与存储后端的集成"""
        # 写入数据
        test_data = {"id": "test1", "value": "test"}
        
        # 创建新的存储实例，验证持久化
        new_storage = CachedJSONStorage[Dict](
            data_dir=str(tmp_path),
            segment="test_index.json"
        )
        
        # 验证数据已持久化
        new_storage.add("key1", test_data)
        assert new_storage.get("key1") == test_data
        
    def test_hash_operations(self, storage):
        """测试哈希相关操作"""
        # 测试数据
        data = [
            {"id": "1", "category": "A", "value": 10},
            {"id": "2", "category": "A", "value": 20},
            {"id": "3", "category": "B", "value": 30}
        ]
        
        # 构建索引
        for i, item in enumerate(data):
            storage.add(f"key{i+1}", item)
            
        # 测试哈希值计算
        hash_a = storage.compute_hash("A")
        hash_b = storage.compute_hash("B")
        assert hash_a != hash_b
        
        # 测试通过哈希查找
        keys_a = storage.get_by_hash(hash_a)
        assert len(keys_a) == 2  # category A 有两条记录
        
        keys_b = storage.get_by_hash(hash_b)
        assert len(keys_b) == 1  # category B 有一条记录
        
    def test_index_update(self, storage):
        """测试索引更新"""
        # 添加初始数据
        storage.add("key1", {"category": "A", "value": 1})
        
        # 获取初始哈希
        hash_a = storage.compute_hash("A")
        assert len(storage.get_by_hash(hash_a)) == 1
        
        # 更新数据
        storage.add("key1", {"category": "B", "value": 1})
        
        # 验证索引更新
        hash_b = storage.compute_hash("B")
        assert len(storage.get_by_hash(hash_a)) == 0  # 旧索引已移除
        assert len(storage.get_by_hash(hash_b)) == 1  # 新索引已添加
        
    def test_hash_collision(self, storage):
        """测试哈希冲突处理"""
        # 添加具有相同哈希值的数据
        data1 = {"value": "test1"}
        data2 = {"value": "test2"}
        
        # 模拟哈希冲突
        hash_value = storage.compute_hash(data1)
        
        storage.add("key1", data1)
        storage.add("key2", data2)
        
        # 验证冲突处理
        keys = storage.get_by_hash(hash_value)
        assert len(keys) == 2
        assert set(keys) == {"key1", "key2"}
        
    @pytest.mark.performance
    def test_batch_performance(self, storage):
        """测试批量操作性能"""
        # 生成测试数据
        num_items = 1000
        start_time = datetime.now()
        
        # 批量添加
        for i in range(num_items):
            storage.add(f"key{i}", {"value": i, "group": i % 10})
            
        duration = (datetime.now() - start_time).total_seconds()
        
        # 验证性能
        assert duration < 5  # 应在5秒内完成
        assert len(storage.list_keys()) == num_items
        
        # 验证索引正确性
        for i in range(10):  # 检查每个分组
            hash_value = storage.compute_hash(i)
            group_keys = storage.get_by_hash(hash_value)
            assert len(group_keys) == num_items // 10