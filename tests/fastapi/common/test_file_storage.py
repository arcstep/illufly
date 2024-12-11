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
    
    storage.set("key1", test_data, "owner1")
    result = storage.get("key1", "owner1")
    
    assert result is not None
    assert result.name == "李四"
    assert result.age == 30

def test_exists(storage_factory: Callable, test_data_factory: Callable):
    """测试exists方法"""
    storage = storage_factory(use_id_subdirs=False)
    
    # 准备测试数据
    test_data1 = test_data_factory(id="1", name="张三", age=25)
    test_data2 = test_data_factory(id="2", name="张三", age=30)
    test_data3 = test_data_factory(id="3", name="李四", age=25)
    
    storage.set("key1", test_data1, "owner1")
    storage.set("key2", test_data2, "owner1")
    storage.set("key3", test_data3, "owner1")
    
    # 测试单个条件查询
    results = storage.exists({"name": "张三"}, "owner1")
    assert len(results) == 2
    
    # 测试多个条件查询
    results = storage.exists({"name": "张三", "age": 25}, "owner1")
    assert len(results) == 1
    assert results[0].id == "1"

