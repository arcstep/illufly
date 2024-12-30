import pytest
import json
import time
from pathlib import Path
from unittest import mock
from typing import Dict, Any

from illufly.io.jiaozi_cache.store import BufferedJSONFileStorageBackend, JSONSerializationError

@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return str(tmp_path)

@pytest.fixture
def storage(temp_dir):
    """创建存储后端实例"""
    storage = BufferedJSONFileStorageBackend(
        data_dir=temp_dir,
        segment="test.json",
        flush_interval=1,
        flush_threshold=5
    )
    yield storage
    storage.close()  # 使用新的close方法

class TestBufferedJSONFileStorageBackend:
    def test_basic_operations(self, storage):
        """测试基本的读写操作"""
        # 写入数据
        data = {"name": "test", "value": 42}
        storage.set("test1", data)
        
        # 立即从内存读取
        result = storage.get("test1")
        assert result == data
        
        # 删除数据
        assert storage.delete("test1")
        assert storage.get("test1") is None

    def test_buffer_strategy(self, storage):
        """测试缓冲策略"""
        # 写入数据但不超过阈值
        for i in range(3):
            storage.set(f"key{i}", {"value": i})
            
        # 检查数据在内存中
        for i in range(3):
            assert storage.get(f"key{i}") == {"value": i}
            
        # 检查文件尚未写入
        file_path = Path(storage._data_dir) / "test.json"
        assert not file_path.exists()
        
        # 继续写入直到超过阈值
        for i in range(3, 6):
            storage.set(f"key{i}", {"value": i})
            
        # 强制刷新
        storage._flush_to_disk()
        
        # 验证文件内容
        assert file_path.exists()
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert len(data) == 6
            for i in range(6):
                assert data[f"key{i}"]["value"] == i

    def test_time_based_flush(self, storage):
        """测试基于时间的刷新"""
        # 写入数据
        storage.set("time_test", {"value": "test"})
        
        # 强制刷新，不依赖定时器
        storage._flush_to_disk()
        
        # 验证文件写入
        file_path = Path(storage._data_dir) / "test.json"
        assert file_path.exists()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data["time_test"]["value"] == "test"

    def test_memory_file_consistency(self, storage):
        """测试内存和文件的一致性"""
        # 写入初始数据
        initial_data = {"key1": {"value": 1}}
        storage.set("key1", initial_data["key1"])
        
        # 强制刷新
        storage._flush_to_disk()
        
        # 修改数据
        updated_data = {"value": 2}
        storage.set("key1", updated_data)
        
        # 验证内存中是新值
        assert storage.get("key1") == updated_data
        
        # 强制刷新
        storage._flush_to_disk()
        
        # 创建新的存储实例读取文件
        new_storage = BufferedJSONFileStorageBackend(
            data_dir=storage._data_dir,
            segment=storage._segment
        )
        
        # 验证新实例读取到的是更新后的值
        assert new_storage.get("key1") == updated_data

    def test_concurrent_modifications(self, storage):
        """测试并发修改"""
        import threading
        
        def writer_thread(start_idx: int):
            for i in range(start_idx, start_idx + 10):
                storage.set(f"concurrent_key_{i}", {"value": i})
                
        # 创建多个写入线程
        threads = [
            threading.Thread(target=writer_thread, args=(i * 10,))
            for i in range(3)
        ]
        
        # 启动所有线程
        for t in threads:
            t.start()
            
        # 等待所有线程完成
        for t in threads:
            t.join()
            
        # 验证所有数据都正确写入
        for i in range(30):
            assert storage.get(f"concurrent_key_{i}") == {"value": i}

    def test_exit_handler(self, storage):
        """测试退出时的数据保存"""
        # 写入数据
        storage.set("exit_test", {"value": "test"})
        
        # 模拟程序退出
        storage._flush_on_exit()
        
        # 验证数据已写入文件
        file_path = Path(storage._data_dir) / "test.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data["exit_test"]["value"] == "test"

    def test_error_handling(self, storage):
        """测试错误处理"""
        # 测试无效数据
        with pytest.raises(JSONSerializationError):
            storage.set("invalid", object())  # 不可序列化的对象
            
        # 测试文件权限错误
        with mock.patch('builtins.open', side_effect=PermissionError("模拟权限错误")):
            with pytest.raises(PermissionError):
                storage.set("permission_test", {"value": "test"})
                storage._flush_to_disk()

    def test_large_dataset(self, storage):
        """测试大数据集性能"""
        # 写入大量数据
        start_time = time.time()
        for i in range(1000):
            storage.set(f"large_key_{i}", {
                "id": i,
                "data": "x" * 100  # 每条数据约100字节
            })
        write_time = time.time() - start_time
        
        # 读取大量数据
        start_time = time.time()
        for i in range(1000):
            assert storage.get(f"large_key_{i}")["id"] == i
        read_time = time.time() - start_time
        
        # 输出性能指标
        print(f"\n写入时间: {write_time:.2f}s")
        print(f"读取时间: {read_time:.2f}s")

    @classmethod
    def teardown_class(cls):
        """测试类结束时的清理工作"""
        # 确保所有可能的定时器都被清理
        import threading
        for timer in threading.enumerate():
            if isinstance(timer, threading.Timer):
                timer.cancel()