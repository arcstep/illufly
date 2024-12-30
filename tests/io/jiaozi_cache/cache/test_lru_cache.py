import pytest
import threading
import time
from typing import Dict, Any
from illufly.io.jiaozi_cache.cache.lru_cache import LRUCacheBackend, CacheEvent

@pytest.fixture
def cache():
    """创建LRU缓存实例"""
    return LRUCacheBackend[Dict](capacity=3)

class TestLRUCacheBackend:
    def test_basic_operations(self, cache):
        """测试基本操作：添加、获取、删除"""
        # 添加
        cache.set("key1", {"value": 1})
        assert cache.get("key1") == {"value": 1}
        
        # 更新
        cache.set("key1", {"value": 2})
        assert cache.get("key1") == {"value": 2}
        
        # 删除
        cache.delete("key1")
        assert cache.get("key1") is None
        
        # 不存在的键
        assert cache.get("nonexistent") is None

    def test_lru_eviction(self, cache):
        """测试LRU淘汰机制"""
        # 填充缓存
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})
        
        # 验证缓存已满
        assert cache.get_stats()["size"] == 3
        
        # 访问key1，使其变为最近使用
        cache.get("key1")
        
        # 添加新键，触发淘汰
        cache.set("key4", {"value": 4})
        
        # key2应该被淘汰（最久未使用）
        assert cache.get("key2") is None
        assert cache.get("key1") == {"value": 1}  # key1应该保留
        assert cache.get("key3") == {"value": 3}  # key3应该保留
        assert cache.get("key4") == {"value": 4}  # key4是新加入的

    def test_eviction_callback(self):
        """测试淘汰回调函数"""
        evicted_keys = []
        
        def on_evict(event: CacheEvent):
            evicted_keys.append(event.key)
            
        cache = LRUCacheBackend[Dict](
            capacity=2,
            on_evict=on_evict
        )
        
        # 触发淘汰
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})  # 应该触发淘汰
        
        assert len(evicted_keys) == 1
        assert evicted_keys[0] == "key1"  # key1应该被淘汰

    def test_concurrent_access(self):
        """测试并发访问"""
        cache = LRUCacheBackend[Dict](capacity=100)
        
        def writer():
            for i in range(50):
                cache.set(f"key{i}", {"value": i})
                time.sleep(0.001)
                
        def reader():
            for i in range(50):
                value = cache.get(f"key{i}")
                if value:
                    assert value["value"] == i
                time.sleep(0.001)
                
        # 创建多个读写线程
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader)
        ]
        
        [t.start() for t in threads]
        [t.join() for t in threads]
        
        # 验证缓存状态
        stats = cache.get_stats()
        assert stats["size"] <= stats["capacity"]

    def test_cache_stats(self, cache):
        """测试缓存统计信息"""
        # 添加数据
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        
        # 命中
        cache.get("key1")
        cache.get("key2")
        
        # 未命中
        cache.get("nonexistent")
        
        # 验证统计
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 2
        assert stats["capacity"] == 3
        assert isinstance(stats["hit_rate"], float)  # 确保是浮点数
        assert pytest.approx(stats["hit_rate"], 0.01) == 2/3  # 使用 pytest.approx 进行浮点数比较

    def test_clear_cache(self, cache):
        """测试清空缓存"""
        # 添加数据
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        
        # 清空缓存
        cache.clear()
        
        # 验证状态
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_update_access_order(self, cache):
        """测试访问顺序更新"""
        # 按顺序添加
        cache.set("key1", {"value": 1})
        cache.set("key2", {"value": 2})
        cache.set("key3", {"value": 3})
        
        # 访问key1，使其变为最近使用
        cache.get("key1")
        
        # 添加新键
        cache.set("key4", {"value": 4})
        
        # key2应该被淘汰（现在是最久未使用的）
        assert cache.get("key2") is None
        assert cache.get("key1") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_exists_check(self, cache):
        """测试键存在性检查"""
        cache.set("key1", {"value": 1})
        
        assert cache.exists("key1")
        assert not cache.exists("nonexistent")
        
        cache.delete("key1")
        assert not cache.exists("key1")

    def test_zero_capacity(self):
        """测试零容量缓存"""
        cache = LRUCacheBackend[Dict](capacity=0)
        
        # 尝试添加数据
        cache.set("key1", {"value": 1})
        
        # 验证数据未被缓存
        assert cache.get("key1") is None
        assert cache.get_stats()["size"] == 0
