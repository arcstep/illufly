import pytest
from typing import Callable
from illufly.fastapi.common.file_storage import FileStorage
from tests.conftest import TestData

def test_set_and_get_direct_mode(storage_factory: Callable, test_data_factory: Callable):
    """测试直接文件模式的设置和获取功能"""
    storage = storage_factory(use_id_subdirs=False)
    test_data = test_data_factory()
    
    storage.set("key1", test_data, "owner1")
    result = storage.get("key1", "owner1")
    
    assert result is not None
    assert result.name == "张三"
    assert result.age == 25

def test_set_and_get_subdir_mode(storage_factory: Callable, test_data_factory: Callable):
    """测试子目录模式的设置和获取功能"""
    storage = storage_factory(use_id_subdirs=True)
    test_data = test_data_factory(name="李四", age=30)
    
    # 在子目录模式下，key参数会被忽略，直接使用owner_id
    storage.set("ignored_key", test_data, "owner1")
    result = storage.get("ignored_key", "owner1")
    
    assert result is not None
    assert result.name == "李四"
    assert result.age == 30

def test_exists_subdir_mode(storage_factory: Callable, test_data_factory: Callable):
    """测试子目录模式下的exists方法"""
    storage = storage_factory(use_id_subdirs=True)
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三", age=25)
    test_data2 = test_data_factory(id="2", name="张三", age=30)
    test_data3 = test_data_factory(id="3", name="李四", age=25)
    
    storage.set("ignored_key", test_data1, "owner1")
    storage.set("ignored_key", test_data2, "owner2")
    storage.set("ignored_key", test_data3, "owner3")
    
    # 测试单个条件查询（不指定owner_id，应该搜索所有目录）
    results = storage.exists({"name": "张三"})
    assert len(results) == 2
    assert {r.id for r in results} == {"1", "2"}
    
    # 测试多个条件查询（不指定owner_id）- 应该返回匹配任一条件的记录
    results = storage.exists({"name": "张三", "age": 25})
    assert len(results) == 3  # 应该匹配所有name=张三或age=25的记录
    assert {r.id for r in results} == {"1", "2", "3"}
    
    # 测试指定owner_id的查询
    results = storage.exists({"name": "张三"}, "owner1")
    assert len(results) == 1
    assert results[0].id == "1"

def test_list_owners(storage_factory: Callable, test_data_factory: Callable):
    """测试list_owners方法"""
    storage = storage_factory(use_id_subdirs=True)
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三")
    test_data2 = test_data_factory(id="2", name="李四")
    test_data3 = test_data_factory(id="3", name="王五")
    
    # 存储数据
    storage.set("ignored_key", test_data1, "owner1")
    storage.set("ignored_key", test_data2, "owner2")
    storage.set("ignored_key", test_data3, "owner3")
    
    # 获取所有owner_id
    owners = storage.list_owners()
    
    # 验证结果
    assert len(owners) == 3
    assert set(owners) == {"owner1", "owner2", "owner3"}

def test_exists_with_partial_match(storage_factory: Callable, test_data_factory: Callable):
    """测试exists方法的部分匹配功能"""
    storage = storage_factory(use_id_subdirs=True)
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三", age=25)
    test_data2 = test_data_factory(id="2", name="李四", age=25)
    test_data3 = test_data_factory(id="3", name="王五", age=30)
    
    storage.set("ignored_key", test_data1, "owner1")
    storage.set("ignored_key", test_data2, "owner2")
    storage.set("ignored_key", test_data3, "owner3")
    
    # 测试多条件匹配 - 应该返回所有匹配任一条件的记录
    results = storage.exists({"name": "张三", "age": 25})
    assert len(results) == 2  # 应该匹配 test_data1 (name=张三) 和 test_data2 (age=25)
    assert {r.id for r in results} == {"1", "2"}
    
    # 测试单个条件匹配
    results = storage.exists({"age": 25})
    assert len(results) == 2  # 应该匹配所有 age=25 的记录
    assert {r.id for r in results} == {"1", "2"}
    
    # 测试不存在的值
    results = storage.exists({"name": "不存在"})
    assert len(results) == 0

