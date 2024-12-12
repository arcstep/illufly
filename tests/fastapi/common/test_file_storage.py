import pytest
from dataclasses import dataclass
from typing import Callable
from illufly.fastapi.common.file_storage import FileConfigStore

@dataclass(frozen=True)
class StorageData:
    """测试用数据类"""
    id: str = "1"
    name: str = "张三"
    age: int = 25
    email: str = "test@example.com"

@pytest.fixture
def test_data_factory():
    def create_test_data(**kwargs):
        defaults = {
            "id": "1",
            "name": "张三",
            "age": 25,
            "email": "test@example.com"
        }
        defaults.update(kwargs)
        return StorageData(**defaults)
    return create_test_data

@pytest.fixture
def storage_factory(tmp_path):
    """创建文件存储实例的工厂函数"""
    def create_storage():
        return FileConfigStore(
            data_dir=str(tmp_path),
            filename="test.json",
            serializer=lambda x: x.__dict__,
            deserializer=lambda x: StorageData(**x)
        )
    return create_storage

def test_set_and_get(storage_factory: Callable, test_data_factory: Callable):
    """测试设置和获取功能"""
    storage = storage_factory()
    test_data = test_data_factory(name="李四", age=30)
    
    storage.set(test_data, "owner1")
    result = storage.get("owner1")
    
    assert result is not None
    assert result.name == "李四"
    assert result.age == 30

def test_list_owners(storage_factory: Callable, test_data_factory: Callable):
    """测试list_owners方法"""
    storage = storage_factory()
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三")
    test_data2 = test_data_factory(id="2", name="李四")
    test_data3 = test_data_factory(id="3", name="王五")
    
    # 存储数据
    storage.set(test_data1, "owner1")
    storage.set(test_data2, "owner2")
    storage.set(test_data3, "owner3")
    
    # 获取所有owner_id
    owners = storage.list_owners()
    
    # 验证结果
    assert len(owners) == 3
    assert set(owners) == {"owner1", "owner2", "owner3"}

def test_has_duplicate(storage_factory: Callable, test_data_factory: Callable):
    """测试唯一性检查"""
    storage = storage_factory()
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三", email="zhangsan@test.com")
    test_data2 = test_data_factory(id="2", name="李四", email="lisi@test.com")
    
    storage.set(test_data1, "owner1")
    storage.set(test_data2, "owner2")
    
    # 测试已存在的唯一值
    assert storage.has_duplicate({"email": "zhangsan@test.com"}) == True
    
    # 测试不存在的唯一值
    assert storage.has_duplicate({"email": "wangwu@test.com"}) == False
    
    # 测试多个属性组合的唯一性
    assert storage.has_duplicate({"name": "张三", "email": "zhangsan@test.com"}) == True
    assert storage.has_duplicate({"name": "张三", "email": "other@test.com"}) == False

def test_find(storage_factory: Callable, test_data_factory: Callable):
    """测试find方法"""
    storage = storage_factory()
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三", age=25)
    test_data2 = test_data_factory(id="2", name="张三", age=30)
    test_data3 = test_data_factory(id="3", name="李四", age=25)
    
    storage.set(test_data1, "owner1")
    storage.set(test_data2, "owner2")
    storage.set(test_data3, "owner3")
    
    # 测试单个条件查询
    results = storage.find({"name": "张三"})
    assert len(results) == 2
    assert {r.id for r in results} == {"1", "2"}
    
    # 测试多个条件的与查询
    results = storage.find({"name": "张三", "age": 25})
    assert len(results) == 1
    assert results[0].id == "1"
    
    # 测试指定owner_id的查询
    results = storage.find({"name": "张三"}, "owner1")
    assert len(results) == 1
    assert results[0].id == "1"

