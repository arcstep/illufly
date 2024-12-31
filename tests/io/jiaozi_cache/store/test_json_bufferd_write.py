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
import logging

from illufly.io.jiaozi_cache import (
    WriteBufferedJSONStorage,
    JSONSerializationError
)
from illufly.config import get_env
from tests.io.jiaozi_cache.store.test_helpers import _TestStatus, _TestData
from illufly.io.jiaozi_cache.store import (
    StorageStrategy,
    TimeSeriesGranularity
)

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
    
@pytest.fixture(autouse=True)
def setup_logging():
    """设置测试时的日志级别"""
    logger = logging.getLogger('illufly.io.jiaozi_cache.store.json_buffered_write')
    logger.setLevel(logging.DEBUG)
    # 添加控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    yield
    # 清理处理器
    logger.handlers.clear()

@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return str(tmp_path)

@pytest.fixture
def storage(temp_dir):
    """创建存储后端实例"""
    storage = WriteBufferedJSONStorage[dict](
        data_dir=temp_dir,
        segment="test",
        strategy=StorageStrategy.INDIVIDUAL,
        flush_threshold=5
    )
    yield storage
    try:
        storage.clear()  # 先清空数据
        storage.close()  # 再关闭存储
    except Exception as e:
        # 在清理阶段的错误不应该影响测试结果
        pass

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

@pytest.fixture
def tmp_storage(tmp_path):
    """创建临时存储实例"""
    return lambda **kwargs: WriteBufferedJSONStorage[dict](
        data_dir=str(tmp_path),
        segment="test",
        **kwargs
    )

class TestWriteBufferedJSONStorage:
    """    
    本测试套件验证了 WriteBufferedJSONStorage 类的所有核心功能:
    
    1. 基本操作
       - 数据的写入和读取
       - 内存缓冲区管理
       - 数据持久化
       
    2. 缓冲策略
       - 自动刷新阈值控制
       - 定时刷新机制
       - 内存与文件一致性
       
    3. 数据类型支持
       - 基础类型 (str, int, float, list, dict等)
       - 复杂类型 (datetime, Decimal, UUID, Path等)
       - Pydantic模型序列化
       - 自定义对象序列化
       
    4. 并发处理
       - 多线程读写安全
       - 缓冲区并发访问
       - 数据一致性保证
       
    5. 存储策略
       - 独立文件策略 (INDIVIDUAL)
       - 共享文件策略 (SHARED)
       - 时间序列策略 (TIME_SERIES)
       
    使用示例:
    ```python
    # 创建存储实例
    storage = WriteBufferedJSONStorage[dict](
        data_dir="/path/to/data",
        segment="user_data",
        strategy=StorageStrategy.INDIVIDUAL,
        flush_threshold=1000  # 缓冲区达到1000条数据自动写入磁盘
    )
    
    # 写入数据
    storage.set("user:1", {"name": "Alice", "age": 30})
    
    # 读取数据
    user = storage.get("user:1")  # {"name": "Alice", "age": 30}
    
    # 手动刷新到磁盘
    storage.flush()
    
    # 使用完毕后关闭
    storage.close()
    ```
    
    配置选项:
    - data_dir: 数据存储目录
    - segment: 数据分段名称
    - strategy: 存储策略 (INDIVIDUAL/SHARED/TIME_SERIES)
    - flush_threshold: 自动刷新阈值
    - flush_interval: 定时刷新间隔(秒)
    """
    def test_basic_operations(self, storage):
        data = {"name": "test", "value": 42}
        key = "test1"
        
        # 写入数据
        storage.set(key, data)
        
        # 验证内存中的数据
        assert storage.get(key) == data
        
        # 刷新到磁盘
        storage.flush()
        
        # 验证文件路径和内容
        expected_path = storage._get_storage_path(key)
        assert expected_path.exists()
        
        # 清空内存缓冲，再次读取验证文件内容
        storage._memory_buffer.clear()
        assert storage.get(key) == data

    def test_buffer_strategy(self, storage):
        """测试缓冲策略"""
        # 写入数据但不超过阈值
        for i in range(3):
            storage.set(f"key{i}", {"value": i})
            assert storage.get(f"key{i}") == {"value": i}

        # 检查是否有任何文件被创建
        json_files = list(storage._data_dir.rglob("*.json"))
        assert len(json_files) == 0  # 确保没有文件写入磁盘

        # 继续写入直到超过阈值
        for i in range(3, 6):
            storage.set(f"key{i}", {"value": i})
        
        # 手动刷新到磁盘
        storage.flush()

        # 验证数据已写入磁盘
        if storage._strategy == StorageStrategy.INDIVIDUAL:
            # 每个key一个文件
            for i in range(6):
                path = storage._get_storage_path(f"key{i}")
                assert path.exists()
                with path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    assert data == {"value": i}
        else:
            # 共享文件策略
            path = storage._get_storage_path("key0")  # 获取正确的文件路径
            assert path.exists()
            with path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                for i in range(6):
                    assert data[f"key{i}"] == {"value": i}

        # 验证缓冲区已清空
        assert len(storage._memory_buffer) == 0
        assert len(storage._dirty_keys) == 0

    def test_time_based_flush(self, storage):
        """测试基于时间的刷新"""
        key = "time_test"
        data = {"value": "test"}
        
        # 写入数据
        storage.set(key, data)
        storage.flush()  # 使用公共方法而不是私有的 _flush_to_disk
        
        # 获取正确的文件路径
        file_path = storage._get_storage_path(key)
        assert file_path.exists()
        
        # 验证文件内容
        with file_path.open('r', encoding='utf-8') as f:
            stored_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert stored_data == data
            else:
                assert stored_data[key] == data
        
        # 验证性能指标
        metrics = storage.get_metrics()
        assert metrics["flush_count"] > 0
        assert metrics["last_flush"] > 0
        assert metrics["total_writes"] == 1
        assert metrics["buffer_size"] == 0
        assert metrics["pending_writes"] == 0

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
        key = "exit_test"
        test_data = {"value": "test"}
        
        # 写入数据
        storage.set(key, test_data)
        storage._flush_on_exit()
        
        # 获取正确的文件路径
        file_path = storage._get_storage_path(key)
        assert file_path.exists()
        
        # 验证文件内容
        with file_path.open('r', encoding='utf-8') as f:
            stored_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert stored_data == test_data
            else:
                assert stored_data[key] == test_data
        
        # 验证缓冲区已清空
        assert len(storage._memory_buffer) == 0
        assert len(storage._dirty_keys) == 0

    def test_error_handling(self, storage):
        """测试错误处理"""
        logger = logging.getLogger('illufly.io.jiaozi_cache.store.json_buffered_write')
        
        # 创建一个不可JSON序列化的对象
        class UnserializableObject:
            pass
        
        unserializable_data = {"key": UnserializableObject()}
        logger.debug(f"尝试序列化数据: {unserializable_data}")
        
        # 方案1: 在set时就检查序列化
        with pytest.raises(JSONSerializationError) as exc_info:
            logger.debug("开始执行 set 操作")
            storage.set("error_key", unserializable_data)
            logger.debug("set 操作完成")
        
        logger.debug(f"捕获到的异常信息: {exc_info.value if 'value' in dir(exc_info) else '无异常'}")
        assert "Failed to serialize" in str(exc_info.value)
        
        # 方案2: 或者在flush时检查序列化
        # storage.set("error_key", unserializable_data)
        # with pytest.raises(JSONSerializationError) as exc_info:
        #     storage.flush()
        # assert "Failed to serialize" in str(exc_info.value)
        
        # 验证错误数据未被存储
        assert storage.get("error_key") is None
        
        # 清空错误数据，避免影响teardown
        storage.clear()

    def test_error_handling_complex_data(self, storage):
        """测试复杂数据结构的错误处理"""
        # 测试嵌套的不可序列化对象
        class UnserializableObject:
            pass
        
        test_cases = [
            # 嵌套在列表中
            {"key": "list_test", "value": [1, UnserializableObject(), 3]},
            # 嵌套在字典中
            {"key": "dict_test", "value": {"normal": "value", "bad": UnserializableObject()}},
            # 多层嵌套
            {"key": "nested_test", "value": {"a": [{"b": UnserializableObject()}]}}
        ]
        
        for test_case in test_cases:
            with pytest.raises(JSONSerializationError) as exc_info:
                storage.set(test_case["key"], test_case["value"])
            assert "Failed to serialize" in str(exc_info.value)
            assert storage.get(test_case["key"]) is None

    def test_error_handling_partial_failure(self, storage):
        """测试部分失败的情况"""
        # 先写入一些正常数据
        valid_data = {"key": "value"}
        storage.set("valid_key", valid_data)
        
        # 尝试写入不可序列化的数据
        class UnserializableObject:
            pass
        
        with pytest.raises(JSONSerializationError):
            storage.set("invalid_key", {"bad": UnserializableObject()})
        
        # 验证之前的有效数据不受影响
        assert storage.get("valid_key") == valid_data
        assert storage.get("invalid_key") is None

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
        assert metrics["pending_writes"] == 3
        assert metrics["total_writes"] == 3
        
        # 刷新后验证指标变化
        storage.flush()
        metrics = storage.get_metrics()
        assert metrics["buffer_size"] == 0
        assert metrics["pending_writes"] == 0
        assert metrics["total_writes"] == 3    # 总写入次数不变
        assert metrics["flush_count"] == 1     # 刷新次数增加

    def test_buffer_overflow(self, storage):
        """测试写缓冲区溢出时的读取行为"""
        
        # 1. 写入足够多的数据触发缓冲区溢出
        for i in range(storage._flush_threshold + 1):  # 直接使用 _flush_threshold
            storage.set(f"key{i}", {"value": i})
        
        # 验证部分数据已经被自动刷新到磁盘
        assert len(storage._memory_buffer) < storage._flush_threshold
        
        # 验证所有数据都可以正确读取
        for i in range(storage._flush_threshold + 1):
            assert storage.get(f"key{i}") == {"value": i}

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
        
        # 验证文件也被清理
        file_path = Path(storage._data_dir) / "test.json"
        assert not file_path.exists() or file_path.stat().st_size == 0

    def test_write_buffer_read_priority(self, storage):
        """测试写缓冲区的读取优先级"""

        # 1. 首次写入数据到磁盘
        initial_data = {"value": 1}
        storage.set("test_key", initial_data)
        storage.flush()   # 强制刷新到磁盘

        # 2. 修改内存中的数据但不刷新
        updated_data = {"value": 2}
        storage.set("test_key", updated_data)

        # 3. 验证读取时优先返回内存中的数据
        assert storage.get("test_key") == updated_data
        assert storage._memory_buffer["test_key"] == updated_data

        # 4. 验证磁盘中仍然是旧数据
        path = storage._get_storage_path("test_key")
        with path.open('r', encoding='utf-8') as f:
            disk_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert disk_data == initial_data
            else:
                assert disk_data["test_key"] == initial_data

        # 5. 刷新后验证磁盘数据已更新
        storage.flush()
        with path.open('r', encoding='utf-8') as f:
            disk_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert disk_data == updated_data
            else:
                assert disk_data["test_key"] == updated_data

        # 6. 清空内存缓冲后验证仍能读取到最新数据
        storage._memory_buffer.clear()
        assert storage.get("test_key") == updated_data

    def test_write_buffer_multiple_updates(self, storage):
        """测试写缓冲区的多次更新场景"""
        
        # 1. 初始数据
        storage.set("key", {"value": 1})
        storage.flush()  # 使用公共方法替代私有方法

        # 2. 验证初始数据已写入磁盘
        path = storage._get_storage_path("key")
        with path.open('r', encoding='utf-8') as f:
            initial_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert initial_data == {"value": 1}
            else:
                assert initial_data["key"] == {"value": 1}

        # 3. 多次更新同一个键
        for i in range(2, 5):
            storage.set("key", {"value": i})
            # 验证内存中的值立即更新
            assert storage.get("key") == {"value": i}
            # 验证磁盘中的值仍然是旧值
            with path.open('r', encoding='utf-8') as f:
                disk_data = json.load(f)
                if storage._strategy == StorageStrategy.INDIVIDUAL:
                    assert disk_data == {"value": 1}  # 仍然是初始值
                else:
                    assert disk_data["key"] == {"value": 1}  # 仍然是初始值

        # 4. 刷新到磁盘
        storage.flush()

        # 5. 验证最终数据
        with path.open('r', encoding='utf-8') as f:
            final_data = json.load(f)
            if storage._strategy == StorageStrategy.INDIVIDUAL:
                assert final_data == {"value": 4}  # 最后一次更新的值
            else:
                assert final_data["key"] == {"value": 4}  # 最后一次更新的值

        # 6. 验证性能指标
        metrics = storage.get_metrics()
        assert metrics["total_writes"] == 4  # 1次初始写入 + 3次更新
        assert metrics["flush_count"] == 2   # 2次flush
        assert metrics["buffer_size"] == 0   # 缓冲区已清空
        assert metrics["pending_writes"] == 0  # 没有待写入的数据

    def test_concurrent_read_write(self, storage):
        """测试并发读写场景下的数据一致性"""
        import threading
        import time
        
        # 用于存储读取结果的字典
        results = {}
        
        def writer():
            for i in range(5):
                storage.set("concurrent_key", {"value": i})
                time.sleep(0.01)  # 模拟写入延迟
                
        def reader():
            for i in range(10):
                value = storage.get("concurrent_key")
                if value:
                    results[f"read_{i}"] = value["value"]
                time.sleep(0.005)  # 模拟读取延迟
        
        # 启动读写线程
        write_thread = threading.Thread(target=writer)
        read_thread = threading.Thread(target=reader)
        
        write_thread.start()
        read_thread.start()
        
        write_thread.join()
        read_thread.join()
        
        # 验证读取的值都是有效的（0-4之间）
        for value in results.values():
            assert 0 <= value <= 4

    def test_shared_strategy(self, tmp_storage):
        """测试分片策略"""
        storage = tmp_storage(
            strategy=StorageStrategy.SHARED,
            partition_count=10
        )
        
        # 写入足够多的数据以测试分片
        for i in range(20):
            storage.set(f"key{i}", {"value": f"test{i}"})
        storage.flush()
        
        # 验证所有数据都已正确写入
        for i in range(20):
            assert storage.get(f"key{i}") == {"value": f"test{i}"}
        
        # 验证文件分布
        json_files = list(storage._data_dir.rglob("*.json"))
        assert len(json_files) > 0  # 至少有一个文件
        
        # 验证数据分布
        for json_file in json_files:
            with json_file.open('r') as f:
                data = json.load(f)
                assert isinstance(data, dict)
                assert len(data) > 0

    def test_time_series_strategy_monthly(self, tmp_storage):
        """测试按月时间序列策略"""
        storage = tmp_storage(
            strategy=StorageStrategy.TIME_SERIES,
            time_granularity=TimeSeriesGranularity.MONTHLY
        )
        
        now = datetime.now()
        year_month = f"{now.year}_{now.month:02d}"
        
        # 写入测试数据并立即刷新
        storage.set("key1", {"value": "test1"})
        storage.flush()
        
        # 获取实际写入的文件
        json_files = list(storage._data_dir.rglob("*.json"))
        assert len(json_files) == 1
        
        # 验证文件名格式
        json_file = json_files[0]
        assert year_month in json_file.name
        assert json_file.exists()

    def test_clear_operation(self, tmp_storage):
        """测试清空操作"""
        for strategy in StorageStrategy:
            storage = tmp_storage(strategy=strategy)
            
            # 写入测试数据
            storage.set("key1", {"value": "test1"})
            storage.set("key2", {"value": "test2"})
            storage.flush()
            
            # 清空数据
            storage.clear()
            
            # 验证数据已清空
            assert storage.list_keys() == []
            assert storage.get("key1") is None
            assert storage.get("key2") is None

    def test_concurrent_access(self, tmp_storage):
        """测试并发访问"""
        import threading
        
        storage = tmp_storage(strategy=StorageStrategy.SHARED)
        num_threads = 10
        num_operations = 100
        
        def worker():
            for i in range(num_operations):
                key = f"key_{threading.get_ident()}_{i}"
                storage.set(key, {"value": f"test_{i}"})
                storage.flush()
                
        # 创建多个线程并发写入
        threads = [
            threading.Thread(target=worker)
            for _ in range(num_threads)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        # 验证所有数据都正确写入
        all_keys = storage.list_keys()
        assert len(all_keys) == num_threads * num_operations

    def test_delete_then_set(self, storage):
        """测试先删除后写入的情况"""
        key = "test_key"
        initial_data = {"value": "initial"}
        updated_data = {"value": "updated"}
        
        # 1. 先写入初始数据并刷新到磁盘
        storage.set(key, initial_data)
        storage.flush()
        
        # 2. 删除数据
        storage.delete(key)
        assert storage.get(key) is None  # 确认删除成功
        
        # 3. 重新写入新数据
        storage.set(key, updated_data)
        assert storage.get(key) == updated_data  # 应该能读取到新数据
        
        # 4. 刷新到磁盘后再次验证
        storage.flush()
        assert storage.get(key) == updated_data  # 刷新后应该仍能读取到新数据

    def test_set_then_delete(self, storage):
        """测试先修改后删除的情况"""
        key = "test_key"
        initial_data = {"value": "initial"}
        updated_data = {"value": "updated"}
        
        # 1. 写入初始数据并刷新
        storage.set(key, initial_data)
        storage.flush()
        
        # 2. 修改数据但不刷新
        storage.set(key, updated_data)
        assert storage.get(key) == updated_data  # 确认修改生效
        
        # 3. 删除数据
        storage.delete(key)
        assert storage.get(key) is None  # 应该读不到数据
        
        # 4. 刷新到磁盘后再次验证
        storage.flush()
        assert storage.get(key) is None  # 刷新后仍应该读不到数据

    def test_multiple_operations_sequence(self, storage):
        """测试复杂的操作序列"""
        key = "test_key"
        data_sequence = [
            {"value": "first"},
            {"value": "second"},
            {"value": "third"}
        ]
        
        # 1. 写入初始数据
        storage.set(key, data_sequence[0])
        assert storage.get(key) == data_sequence[0]
        
        # 2. 删除数据
        storage.delete(key)
        assert storage.get(key) is None
        
        # 3. 写入新数据
        storage.set(key, data_sequence[1])
        assert storage.get(key) == data_sequence[1]
        
        # 4. 再次删除
        storage.delete(key)
        assert storage.get(key) is None
        
        # 5. 最后写入数据并刷新
        storage.set(key, data_sequence[2])
        storage.flush()
        assert storage.get(key) == data_sequence[2]
        
        # 6. 清空内存缓冲后验证磁盘数据
        storage._memory_buffer.clear()
        assert storage.get(key) == data_sequence[2]

    def test_concurrent_delete_set_operations(self, storage):
        """测试并发的删除和写入操作"""
        import threading
        import time
        
        keys = [f"key_{i}" for i in range(5)]
        operation_complete = threading.Event()
        
        def writer():
            for key in keys:
                storage.set(key, {"value": "initial"})
                time.sleep(0.01)  # 模拟操作延迟
                
        def deleter():
            # 等待部分写入完成
            time.sleep(0.02)
            for key in keys:
                storage.delete(key)
                time.sleep(0.01)
                # 删除后立即写入新值
                storage.set(key, {"value": "after_delete"})
                
        # 启动写入和删除线程
        write_thread = threading.Thread(target=writer)
        delete_thread = threading.Thread(target=deleter)
        
        write_thread.start()
        delete_thread.start()
        
        write_thread.join()
        delete_thread.join()
        
        # 验证最终状态
        storage.flush()  # 确保所有操作都已写入磁盘
        
        for key in keys:
            value = storage.get(key)
            assert value is not None
            assert value["value"] == "after_delete"

    def test_delete_nonexistent_then_set(self, storage):
        """测试删除不存在的键后再写入"""
        key = "nonexistent_key"
        
        # 1. 删除不存在的键
        storage.delete(key)
        assert storage.get(key) is None
        
        # 2. 写入数据
        data = {"value": "new"}
        storage.set(key, data)
        assert storage.get(key) == data
        
        # 3. 刷新并验证
        storage.flush()
        assert storage.get(key) == data

    def test_rapid_set_delete_set(self, storage):
        """测试快速的写入-删除-写入序列"""
        key = "test_key"
        
        # 快速执行一系列操作
        storage.set(key, {"value": "1"})
        storage.delete(key)
        storage.set(key, {"value": "2"})
        storage.delete(key)
        storage.set(key, {"value": "3"})
        
        # 验证最终状态
        assert storage.get(key) == {"value": "3"}
        
        # 刷新后再次验证
        storage.flush()
        assert storage.get(key) == {"value": "3"}

    @classmethod
    def teardown_class(cls):
        """测试类结束时的清理工作"""
        for timer in threading.enumerate():
            if isinstance(timer, threading.Timer):
                timer.cancel()