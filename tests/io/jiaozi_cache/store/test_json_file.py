import pytest
import json
import time
import threading
from pathlib import Path
from unittest import mock
from typing import Dict, Any
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from illufly.io.jiaozi_cache.store.json_file import (
    BufferedJSONFileStorageBackend,
    JSONSerializationError
)
from tests.io.jiaozi_cache.store.test_helpers import _TestStatus, _TestData  # 从辅助模块导入

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
    storage.close()

@pytest.fixture
def test_data():
    """测试数据"""
    return {
        "string": "test",
        "int": 42,
        "float": 3.14,
        "list": [1, 2, 3],
        "dict": {"key": "value"},
        "tuple": (1, 2, 3),
        "datetime": datetime.now(),
        "decimal": Decimal("3.14"),
        "uuid": UUID("550e8400-e29b-41d4-a716-446655440000"),
        "path": Path("/test/path"),
        "enum": _TestStatus.ACTIVE,
        "custom": _TestData("test", 42),
        "nested": {
            "list": [{"key": "value"}, 1, "test"],
            "dict": {"key": {"nested": "value"}}
        }
    }

class TestBufferedJSONFileStorageBackend:
    def test_basic_operations(self, storage):
        """测试基本的读写操作"""
        data = {"name": "test", "value": 42}
        storage.set("test1", data)
        assert storage.get("test1") == data
        assert storage.delete("test1")
        assert storage.get("test1") is None

    def test_buffer_strategy(self, storage):
        """测试缓冲策略"""
        # 写入数据但不超过阈值
        for i in range(3):
            storage.set(f"key{i}", {"value": i})
            assert storage.get(f"key{i}") == {"value": i}
            
        file_path = Path(storage._data_dir) / "test.json"
        assert not file_path.exists()
        
        # 继续写入直到超过阈值并验证
        for i in range(3, 6):
            storage.set(f"key{i}", {"value": i})
        storage._flush_to_disk()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert len(data) == 6
            assert all(data[f"key{i}"]["value"] == i for i in range(6))

    def test_time_based_flush(self, storage):
        """测试基于时间的刷新"""
        storage.set("time_test", {"value": "test"})
        storage._flush_to_disk()
        
        file_path = Path(storage._data_dir) / "test.json"
        with open(file_path, 'r', encoding='utf-8') as f:
            assert json.load(f)["time_test"]["value"] == "test"

    def test_memory_file_consistency(self, storage):
        """测试内存和文件的一致性"""
        storage.set("key1", {"value": 1})
        storage._flush_to_disk()
        storage.set("key1", {"value": 2})
        assert storage.get("key1") == {"value": 2}
        storage._flush_to_disk()
        
        new_storage = BufferedJSONFileStorageBackend(
            data_dir=storage._data_dir,
            segment=storage._segment
        )
        assert new_storage.get("key1") == {"value": 2}

    def test_concurrent_modifications(self, storage):
        """测试并发修改"""
        def writer_thread(start_idx: int):
            for i in range(start_idx, start_idx + 10):
                storage.set(f"concurrent_key_{i}", {"value": i})
                
        threads = [threading.Thread(target=writer_thread, args=(i * 10,)) for i in range(3)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        
        assert all(storage.get(f"concurrent_key_{i}") == {"value": i} for i in range(30))

    def test_exit_handler(self, storage):
        """测试退出时的数据保存"""
        storage.set("exit_test", {"value": "test"})
        storage._flush_on_exit()
        
        with open(Path(storage._data_dir) / "test.json", 'r', encoding='utf-8') as f:
            assert json.load(f)["exit_test"]["value"] == "test"

    def test_error_handling(self, storage):
        """测试错误处理"""
        with pytest.raises(JSONSerializationError):
            storage.set("invalid", object())

    def test_large_dataset(self, storage):
        """测试大数据集性能"""
        start = time.time()
        [storage.set(f"large_key_{i}", {"id": i, "data": "x" * 100}) for i in range(1000)]
        write_time = time.time() - start
        
        start = time.time()
        assert all(storage.get(f"large_key_{i}")["id"] == i for i in range(1000))
        read_time = time.time() - start
        
        print(f"\n写入时间: {write_time:.2f}s")
        print(f"读取时间: {read_time:.2f}s")

    def test_complex_data_types(self, storage, test_data):
        """测试复杂数据类型的序列化"""
        storage.set("complex", test_data)
        result = storage.get("complex")
        
        # 验证基本类型
        assert result["string"] == test_data["string"]
        assert result["int"] == test_data["int"]
        assert result["float"] == test_data["float"]
        assert result["list"] == test_data["list"]
        assert result["dict"] == test_data["dict"]
        assert tuple(result["tuple"]) == test_data["tuple"]
        
        # 验证复杂类型
        assert isinstance(result["datetime"], datetime)
        assert isinstance(result["decimal"], Decimal)
        assert isinstance(result["uuid"], UUID)
        assert isinstance(result["path"], Path)
        assert result["enum"] == test_data["enum"]
        assert isinstance(result["enum"], _TestStatus)
        assert result["enum"].value == test_data["enum"].value
        assert result["enum"].name == test_data["enum"].name
        
        # 验证自定义对象
        assert isinstance(result["custom"], _TestData)  # 首先验证类型
        assert result["custom"].name == test_data["custom"].name  # 然后验证属性
        assert result["custom"].value == test_data["custom"].value
        # 或者比较字典形式
        assert result["custom"].to_dict() == test_data["custom"].to_dict()
        assert result["nested"] == test_data["nested"]

    @classmethod
    def teardown_class(cls):
        """测试类结束时的清理工作"""
        for timer in threading.enumerate():
            if isinstance(timer, threading.Timer):
                timer.cancel()