from dataclasses import dataclass, asdict
from typing import Callable
import pytest
import logging
import time

from illufly.io import JiaoziCache
from tests.io.jiaozi_cache.conftest import StorageData  # 使用绝对导入路径

class TestSimpleStorageData:
    @pytest.fixture(autouse=True)
    def setup_env(self):
        import os
        os.environ["JIAOZI_CACHE_FULL_SCAN_THRESHOLD"] = "1"

    @pytest.fixture
    def test_data_factory(self, tmp_path):
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

    @pytest.fixture(autouse=True)
    def setup_logging(self):
        """设置日志级别为DEBUG"""
        # 配置根日志记录器
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True
        )
        
        logger = logging.getLogger('illufly')
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        logger.propagate = True
        yield
        logger.handlers.clear()

    def test_set_and_get(self, storage_factory: Callable, test_data_factory: Callable):
        """测试设置和获取功能"""
        storage = storage_factory()
        test_data = test_data_factory(name="李四", age=30)
        
        storage.set(test_data, "owner1")
        result = storage.get("owner1")
        
        assert result is not None
        assert result.name == "李四"
        assert result.age == 30

    def test_list_owners(self, storage_factory: Callable, test_data_factory: Callable):
        """测试list_owners方法"""
        
        # 准备测试数据
        storage = storage_factory()
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

    def test_delete(self, storage_factory: Callable, test_data_factory: Callable, tmp_path):
        """测试删除功能"""
        storage = storage_factory()
        test_data = test_data_factory(name="张三", age=25)
        
        # 存储数据
        storage.set(test_data, "owner1")
        
        # 验证数据存在
        assert storage.get("owner1") is not None
        
        # 删除数据
        result = storage.delete("owner1")
        assert result is True  # 确认删除成功
        
        # 验证数据已被删除
        assert storage.get("owner1") is None
        assert "owner1" not in storage.list_owners()
        
        # 测试删除不存在的数据
        result = storage.delete("non_existent_owner")
        assert result is False  # 确认删除不存在的数据返回False

    def test_delete_with_multiple_files(self, tmp_path, test_data_factory):
        """测试在同一目录下有多个文件时的删除功能"""
        # 创建两个不同的存储实例，确保指定索引
        storage1 = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test1.json",
            data_class=StorageData,
            indexes=[]  # 显式指定空索引列表
        )
        storage2 = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test2.json",
            data_class=StorageData,
            indexes=[]  # 显式指定空索引列表
        )
        
        test_data = test_data_factory(name="张三", age=25)
        
        storage1.set(test_data, "owner1")
        storage2.set(test_data, "owner1")
        
        assert storage1.get("owner1") is not None
        assert storage2.get("owner1") is not None
        
        result = storage1.delete("owner1")
        assert result is True
        
        assert storage1.get("owner1") is None
        assert storage2.get("owner1") is not None
        assert (tmp_path / "owner1").exists()

    def test_find_with_index(self, tmp_path, test_data_factory: Callable):
        """测试使用索引的唯一性检查"""
        storage = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test.json",
            data_class=StorageData,
            indexes=["email"]
        )
        
        # 准备测试数据
        test_data1 = test_data_factory(id="1", name="张三", email="zhangsan@test.com")
        test_data2 = test_data_factory(id="2", name="李四", email="lisi@test.com")
        
        storage.set(test_data1, "owner1")
        storage.set(test_data2, "owner2")
        
        # 验证索引已建立
        assert "email" in storage._index._indexes
        assert storage._index._indexes["email"]["zhangsan@test.com"] == ["owner1"]
        
        # 使用索引字段进行查询
        results = storage.find({"email": "zhangsan@test.com"})
        assert len(results) == 1
        assert results[0].email == "zhangsan@test.com"
        assert results[0].name == "张三"
        
        # 测试不存在的值
        results = storage.find({"email": "wangwu@test.com"})
        assert len(results) == 0
        
        # 测试组合条件（一个索引字段 + 一个非索引字段）
        results = storage.find({
            "email": "zhangsan@test.com",  # 索引字段
            "name": "张三"  # 非索引字段
        })
        assert len(results) == 1
        assert results[0].email == "zhangsan@test.com"
        assert results[0].name == "张三"
        
        # 测试组合条件不匹配的情况
        results = storage.find({
            "email": "zhangsan@test.com",  # 索引字段
            "name": "李四"  # 非索引字段,不匹配
        })
        assert len(results) == 0

    def test_find_without_index(self, tmp_path, test_data_factory: Callable):
        """测试无索引的查找"""
        storage = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test.json",
            data_class=StorageData,
            indexes=[]
        )

        # 准备测试数据
        test_data1 = test_data_factory(id="1", name="张三", email="zhangsan@test.com")
        test_data2 = test_data_factory(id="2", name="李四", email="lisi@test.com")

        storage.set(test_data1, "owner1")
        storage.set(test_data2, "owner2")

        # 验证确实没有索引
        assert not storage._index._indexes

        # 测试单个属性查找
        with pytest.warns(UserWarning):  # 使用 UserWarning 而不是 RuntimeWarning
            result = storage.find({"email": "zhangsan@test.com"})
            assert len(result) == 1
            assert result[0].email == "zhangsan@test.com"

    def test_find_performance(self, tmp_path, test_data_factory):
        """测试查找性能差异"""
        storage_with_index = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test_indexed.json",
            data_class=StorageData,
            indexes=["email"]
        )

        storage_without_index = JiaoziCache.create_with_json_storage(
            data_dir=str(tmp_path),
            filename="test_no_index.json",
            data_class=StorageData,
            indexes=[]
        )

        # 准备测试数据
        for i in range(100):
            data = test_data_factory(
                id=str(i),
                name=f"user{i}",
                email=f"user{i}@test.com"
            )
            storage_with_index.set(data, f"owner{i}")
            storage_without_index.set(data, f"owner{i}")

        # 测试性能
        start_time = time.time()
        result_with_index = storage_with_index.find({"email": "user99@test.com"})
        index_time = time.time() - start_time

        start_time = time.time()
        with pytest.warns(UserWarning):  # 使用 UserWarning
            result_without_index = storage_without_index.find({"email": "user99@test.com"})
        scan_time = time.time() - start_time

        # 验证结果
        assert len(result_with_index) == 1
        assert len(result_without_index) == 1
        assert result_with_index[0].email == "user99@test.com"
        assert result_without_index[0].email == "user99@test.com"
        assert scan_time > index_time  # 全量扫描应该更慢

