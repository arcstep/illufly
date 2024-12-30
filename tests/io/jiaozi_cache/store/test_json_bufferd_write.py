import pytest
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel

from illufly.io.jiaozi_cache import (
    WriteBufferedJSONStorage,
    JSONSerializationError
)
from illufly.config import get_env
from tests.io.jiaozi_cache.store.test_helpers import _TestStatus, _TestData

# 定义测试用的 Pydantic 模型
class UserAddress(BaseModel):
    street: str
    city: str
    country: str
    postal_code: Optional[str] = None

class UserProfile(BaseModel):
    id: int
    name: str
    email: str
    created_at: datetime
    addresses: List[UserAddress]
    is_active: bool = True
    
@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return str(tmp_path)

@pytest.fixture
def storage(temp_dir):
    """创建存储后端实例"""
    storage = WriteBufferedJSONStorage(
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

@pytest.fixture
def pydantic_test_data():
    """Pydantic测试数据"""
    return UserProfile(
        id=1,
        name="Test User",
        email="test@example.com",
        created_at=datetime.now(),
        addresses=[
            UserAddress(
                street="123 Test St",
                city="Test City",
                country="Test Country",
                postal_code="12345"
            ),
            UserAddress(
                street="456 Sample Ave",
                city="Sample City",
                country="Sample Country"
            )
        ]
    )

def wait_for_flush(storage, timeout=2):
    """等待刷新完成"""
    start = time.time()
    while time.time() - start < timeout:
        if not storage._is_flushing:
            return True
        time.sleep(0.1)
    return False

class TestWriteBufferedJSONStorage:
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
        
        new_storage = WriteBufferedJSONStorage(
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

    def test_pydantic_serialization(self, storage, pydantic_test_data):
        """测试Pydantic模型的序列化"""
        # 存储Pydantic对象
        storage.set("user_profile", pydantic_test_data)
        
        # 读取并验证
        result = storage.get("user_profile")
        
        # 验证类型
        assert isinstance(result, UserProfile)
        
        # 验证基本属性
        assert result.id == pydantic_test_data.id
        assert result.name == pydantic_test_data.name
        assert result.email == pydantic_test_data.email
        assert isinstance(result.created_at, datetime)
        assert result.is_active == pydantic_test_data.is_active
        
        # 验证嵌套对象
        assert len(result.addresses) == len(pydantic_test_data.addresses)
        for saved_addr, orig_addr in zip(result.addresses, pydantic_test_data.addresses):
            assert isinstance(saved_addr, UserAddress)
            assert saved_addr.street == orig_addr.street
            assert saved_addr.city == orig_addr.city
            assert saved_addr.country == orig_addr.country
            assert saved_addr.postal_code == orig_addr.postal_code
            
        # 验证模型方法
        assert result.model_dump() == pydantic_test_data.model_dump()

    def test_pydantic_nested_in_dict(self, storage, pydantic_test_data):
        """测试在字典中嵌套Pydantic对象"""
        nested_data = {
            "user": pydantic_test_data,
            "metadata": {
                "tags": ["test", "example"],
                "address": UserAddress(
                    street="789 Nested St",
                    city="Nested City",
                    country="Nested Country"
                )
            }
        }
        
        # 存储嵌套数据
        storage.set("nested_pydantic", nested_data)
        
        # 读取并验证
        result = storage.get("nested_pydantic")
        
        # 验证顶层结构
        assert isinstance(result["user"], UserProfile)
        assert isinstance(result["metadata"]["address"], UserAddress)
        
        # 验证嵌套的Pydantic对象
        assert result["user"].model_dump() == pydantic_test_data.model_dump()
        assert result["metadata"]["tags"] == nested_data["metadata"]["tags"]
        assert result["metadata"]["address"].street == "789 Nested St"

    def test_config_values(self, temp_dir):
        """测试配置值的使用"""
        # 使用默认配置
        storage1 = WriteBufferedJSONStorage(
            data_dir=temp_dir,
            segment="test1.json"
        )
        assert storage1._flush_interval == int(get_env("JIAOZI_CACHE_FLUSH_INTERVAL"))
        assert storage1._flush_threshold == int(get_env("JIAOZI_CACHE_FLUSH_THRESHOLD"))
        
        # 使用自定义配置
        storage2 = WriteBufferedJSONStorage(
            data_dir=temp_dir,
            segment="test2.json",
            flush_interval=30,
            flush_threshold=2000
        )
        assert storage2._flush_interval == 30
        assert storage2._flush_threshold == 2000

    def test_buffer_metrics(self, storage):
        """测试缓冲区指标"""
        # 写入数据
        for i in range(3):
            storage.set(f"key{i}", {"value": i})
        
        # 获取指标
        metrics = storage.get_metrics()
        assert metrics["buffer_size"] == 3
        assert metrics["dirty_count"] == 3
        assert metrics["modify_count"] == 3
        assert isinstance(metrics["last_flush"], float)

    def test_buffer_overflow(self, storage):
        """测试缓冲区溢出处理"""
        threshold = storage._flush_threshold
        
        # 写入直到超过阈值
        for i in range(threshold + 1):
            storage.set(f"key{i}", {"value": i})
            
        # 强制刷新确保所有数据写入
        storage._flush_to_disk()
        
        # 验证自动刷新
        file_path = Path(storage._data_dir) / "test.json"
        assert file_path.exists()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert len(data) == threshold + 1  # 现在应该能通过了

    def test_concurrent_buffer_access(self, storage):
        """测试并发缓冲区访问"""
        def writer(start_idx: int, count: int):
            for i in range(start_idx, start_idx + count):
                storage.set(f"concurrent_key_{i}", {"value": i})
                time.sleep(0.01)  # 模拟实际操作延迟
                
        def reader(keys: List[str]):
            for key in keys:
                value = storage.get(key)
                if value is not None:
                    assert isinstance(value["value"], int)
        
        # 创建多个写入线程和读取线程
        writers = [
            threading.Thread(target=writer, args=(i * 10, 10))
            for i in range(3)
        ]
        readers = [
            threading.Thread(
                target=reader,
                args=([f"concurrent_key_{i}" for i in range(j * 10, (j + 1) * 10)],)
            )
            for j in range(3)
        ]
        
        # 启动所有线程
        all_threads = writers + readers
        [t.start() for t in all_threads]
        [t.join() for t in all_threads]
        
        # 验证数据完整性
        storage._flush_to_disk()  # 确保所有数据都已写入
        for i in range(30):
            value = storage.get(f"concurrent_key_{i}")
            assert value is not None
            assert value["value"] == i

    def test_buffer_clear(self, storage):
        """测试缓冲区清理"""
        # 写入数据
        for i in range(5):
            storage.set(f"key{i}", {"value": i})
            
        # 清理缓冲区
        storage.clear()
        
        # 验证缓冲区已清空
        metrics = storage.get_metrics()
        assert metrics["buffer_size"] == 0
        assert metrics["dirty_count"] == 0
        assert metrics["modify_count"] == 0
        
        # 验证文件也被清理
        file_path = Path(storage._data_dir) / "test.json"
        assert not file_path.exists() or file_path.stat().st_size == 0

    @classmethod
    def teardown_class(cls):
        """测试类结束时的清理工作"""
        for timer in threading.enumerate():
            if isinstance(timer, threading.Timer):
                timer.cancel()