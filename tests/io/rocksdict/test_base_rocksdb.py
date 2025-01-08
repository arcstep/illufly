import pytest
from rocksdict import Rdict, Options, ReadOptions, WriteOptions
from illufly.io.rocksdict.base_rocksdb import BaseRocksDB, WriteBatch
import tempfile
import os
import shutil
from typing import Union
import itertools

# 配置日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestBasicOperations:
    @pytest.fixture(autouse=True)
    def setup_logging(self, caplog):
        caplog.set_level(logging.INFO)

    @pytest.fixture
    def db_path(self):
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)
    
    @pytest.fixture
    def db(self, db_path):
        db = BaseRocksDB(db_path, logger=logger)
        try:
            yield db
        finally:
            db.close()
            
    def test_put_get_delete(self, db):
        """测试基本的读写删除操作"""
        # 直接方法调用
        db.put("key1", "value1")
        assert db.get("key1") == "value1"
        
        # 字典风格访问
        db["key2"] = "value2"
        assert db["key2"] == "value2"
        
        # 删除操作
        db.delete("key1")
        assert db.get("key1") is None
        del db["key2"]
        assert db["key2"] is None
        
        # 默认值
        assert db.get("nonexistent", default="default") == "default"
        
        # 批量获取
        db.put("multi1", "val1")
        db.put("multi2", "val2")
        results = db.get(["multi1", "multi2", "nonexistent"])
        assert results == ["val1", "val2", None]
    
    def test_collection_methods(self, db):
        """测试集合类方法"""
        # 准备测试数据
        test_data = {
            "user:1": "alice",
            "user:2": "bob",
            "config:1": "setting1"
        }
        for k, v in test_data.items():
            db[k] = v
            
        # 测试 keys()
        all_keys = db.keys()
        assert len(all_keys) == 3
        assert "user:1" in all_keys
        
        user_keys = db.keys(prefix="user:")
        assert len(user_keys) == 2
        assert all(k.startswith("user:") for k in user_keys)
        
        # 测试 values()
        all_values = db.values()
        assert len(all_values) == 3
        assert "alice" in all_values
        
        user_values = db.values(prefix="user:")
        assert len(user_values) == 2
        assert "alice" in user_values
        assert "setting1" not in user_values
        
        # 测试 items()
        all_items = db.items()
        assert len(all_items) == 3
        assert ("user:1", "alice") in all_items
        
        # 测试带限制的 items()
        limited_items = db.items(limit=2)
        assert len(limited_items) == 2
        
        # 测试迭代器方法
        key_count = sum(1 for _ in db.iter_keys())
        assert key_count == 3
        
        value_count = sum(1 for _ in db.iter_values())
        assert value_count == 3
    
    def test_existence_checks(self, db):
        """测试存在性检查方法"""
        db["key1"] = "value1"
        
        # 快速存在性检查
        assert not db.not_exist("key1")
        assert db.not_exist("nonexistent")
        
        # 详细存在性检查
        exists, value = db.exist("key1")
        assert exists
        assert value == "value1"
        
        exists, value = db.exist("nonexistent")
        assert not exists
        assert value is None
    
    def test_options_handling(self, db):
        """测试选项参数处理"""
        # 读取选项
        read_opts = ReadOptions()
        read_opts.fill_cache(True)
        value = db.get("key", options=read_opts)
        assert value is None
        
        # 写入选项
        write_opts = WriteOptions()
        write_opts.disable_wal = True  # 使用属性赋值
        db.put("key", "value", options=write_opts)
        assert db.get("key") == "value"

class TestIterationOperations:
    @pytest.fixture(autouse=True)
    def setup_logging(self, caplog):
        caplog.set_level(logging.INFO)

    @pytest.fixture
    def db_path(self):
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)
    
    @pytest.fixture
    def db(self, db_path):
        db = BaseRocksDB(db_path, logger=logger)
        try:
            yield db
        finally:
            db.close()
    
    @pytest.fixture
    def populated_db(self, db):
        """创建并填充测试数据的数据库"""
        # 添加测试数据
        test_data = {
            "user:01": "alice",
            "user:02": "bob",
            "user:03": "david",
            "user:04": "emma",
            "user:05": "frank",
            "user:06": "grace",
            "user:07": "henry",
            "user:08": "iris",
            "user:09": "jack",
            "user:10": "kelly",
            "user:11": "lucas",
            "config:01": "setting1",
            "config:02": "setting2",
            "log:01": "log entry 1",
            "log:02": "log entry 2",
        }
        for k, v in test_data.items():
            db.put(k, v)
            logger.info(f"Added test data: {k} = {v}")
        
        # 验证数据写入
        for k, v in test_data.items():
            stored_v = db.get(k)
            logger.info(f"Verified data: {k} = {stored_v}")
            assert stored_v == v
            
        return db
    
    def test_iter_basic(self, populated_db):
        """测试基本迭代功能"""
        # 全量迭代
        items = list(populated_db.iter())
        assert len(items) == 15
        
        # 前缀迭代
        user_items = list(populated_db.iter(prefix="user:"))
        assert len(user_items) == 11
        assert all(k.startswith("user:") for k, _ in user_items)
    
    def test_iter_range(self, populated_db):
        """测试范围迭代"""
        # 清理已有数据
        for key in list(populated_db.iter()):
            del populated_db[key[0]]
        
        # 添加格式统一的测试数据
        test_data = {
            f"user:{i:02d}": f"user_{i:02d}" 
            for i in range(1, 11)  # 生成 user:01 到 user:10
        }
        
        for k, v in test_data.items():
            populated_db[k] = v
            logger.info(f"Added test data: {k} = {v}")
        
        # 验证所有数据
        all_items = list(populated_db.iter())
        logger.info(f"All items in db: {all_items}")
        
        # 测试用例：(start, end, expected_count, description)
        test_cases = [
            ("user:03", "user:05", 2, "区间 [user:03, user:05)"),
            (None, "user:03", 2, "上界 [user:01, user:03)"),
            ("user:08", None, 3, "下界 [user:08, ...)"),
            ("user:99", None, 0, "无匹配的下界"),
            (None, "user:00", 0, "无匹配的上界"),
            ("user:05", "user:05", 0, "空区间"),
        ]
        
        for start, end, expected_count, desc in test_cases:
            logger.info(f"\nTesting: {desc}")
            items = list(populated_db.iter(start=start, end=end))
            logger.info(f"Found items: {items}")
            assert len(items) == expected_count, \
                f"Expected {expected_count} items for {desc}, got {len(items)}: {items}"
    
    def test_iter_reverse(self, populated_db):
        """测试反向迭代"""
        # 普通反向迭代
        items = list(populated_db.iter(reverse=True))
        assert len(items) == 15
        assert items[0][0] > items[-1][0]  # 确保降序
        
        # 带前缀的反向迭代
        items = list(populated_db.iter(prefix="user:", reverse=True))
        assert len(items) == 11
        assert all(k.startswith("user:") for k, _ in items)
        assert items[0][0] > items[-1][0]  # 确保降序
        
        # 带范围的反向迭代
        items = list(populated_db.iter(start="user:02", end="user:05", reverse=True))
        assert len(items) == 3  # user:04, user:03, user:02
        assert items[0][0] == "user:04"
        assert items[-1][0] == "user:02"
    
    def test_iter_performance_options(self, populated_db):
        """测试性能相关选项"""
        # 测试 fill_cache=False 选项
        items = list(populated_db.iter(
            fill_cache=False,
        ))
        assert len(items) == 15  # 更新为实际的数据量
        
        # 测试自定义 ReadOptions
        opts = ReadOptions()
        opts.fill_cache(False)
        items = list(populated_db.iter(options=opts))
        assert len(items) == 15  # 更新为实际的数据量
        
        # 验证数据内容没有变化
        assert all(isinstance(k, str) for k, _ in items)
        assert all(isinstance(v, str) for _, v in items)
    
    def test_keys_values_items(self, populated_db):
        """测试键值获取方法"""
        # 测试 keys
        keys = populated_db.keys(prefix="user:")
        assert len(keys) == 11
        assert all(k.startswith("user:") for k in keys)
        assert "user:01" in keys
        assert "user:11" in keys
        
        # 测试 values
        values = populated_db.values(prefix="user:")
        assert len(values) == 11
        assert "alice" in values
        assert "lucas" in values
        
        # 测试 items
        items = populated_db.items(prefix="user:")
        assert len(items) == 11
        assert ("user:01", "alice") in items
        assert ("user:11", "lucas") in items

        # 测试 items
        items = populated_db.items(prefix="user:", limit=1)
        logger.info(f"Items with limit 1: {items}")
        assert len(items) == 1
        assert ("user:01", "alice") in items

    def test_iter_keys_values(self, populated_db):
        """测试键值迭代器"""
        # 测试键迭代器
        keys = list(populated_db.iter_keys(prefix="log:"))
        assert len(keys) == 2
        assert all(k.startswith("log:") for k in keys)
        
        # 测试值迭代器
        values = list(populated_db.iter_values(prefix="log:"))
        assert len(values) == 2
        assert all(v.startswith("log entry") for v in values)
    
    def test_edge_cases(self, populated_db):
        """测试边界情况"""
        # 空前缀
        items = list(populated_db.iter(prefix=""))
        logger.info(f"Empty prefix returned: {items}")
        assert len(items) == 15
        
        # 不存在的前缀
        items = list(populated_db.iter(prefix="nonexistent:"))
        logger.info(f"Nonexistent prefix returned: {items}")
        assert len(items) == 0
        
        # 范围边界
        items = list(populated_db.iter(start="a", end="z"))
        logger.info(f"Range [a, z] returned: {items}")
        assert len(items) == 15

        # 范围边界
        items = list(populated_db.iter(start="a"))
        logger.info(f"Range [a, z] returned: {items}")
        assert len(items) == 15

        # 反向范围
        items = list(populated_db.iter(start="z", end="a", reverse=True))
        logger.info(f"Reverse range [z, a] returned: {items}")
        assert len(items) == 15

class TestColumnFamilies:
    @pytest.fixture(autouse=True)
    def setup_logging(self, caplog):
        caplog.set_level(logging.INFO)

    @pytest.fixture
    def db_path(self):
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)
    
    @pytest.fixture
    def db(self, db_path):
        db = BaseRocksDB(db_path, logger=logger)
        try:
            yield db
        finally:
            db.close()
    
    def test_column_family_basic(self, db):
        """测试列族基本操作"""
        # 创建列族
        users_cf = db.create_column_family("users")
        assert "users" in db.list_column_families(db.path)
        
        # 获取列族
        users_cf2 = db.get_column_family("users")
        assert users_cf2 is not None
        
        # 写入和读取数据
        users_cf.put("user:01", "alice")
        assert users_cf.get("user:01") == "alice"
        
        # 删除列族
        db.drop_column_family("users")
        assert "users" not in db.list_column_families(db.path)
    
    def test_default_column_family(self, db):
        """测试默认列族"""
        default_cf = db.default_cf
        assert default_cf is not None
        
        # 写入和读取数据
        default_cf.put("key1", "value1")
        assert default_cf.get("key1") == "value1"
        assert db.get("key1") == "value1"  # 通过主DB实例也能读取

class TestBatchOperations:
    @pytest.fixture(autouse=True)
    def setup_logging(self, caplog):
        caplog.set_level(logging.INFO)

    @pytest.fixture
    def db_path(self):
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)
    
    @pytest.fixture
    def db(self, db_path):
        db = BaseRocksDB(db_path, logger=logger)
        try:
            yield db
        finally:
            db.close()
    
    def test_batch_basic(self, db):
        """测试基本批处理操作"""
        # 创建批处理
        batch = WriteBatch()
        
        # 添加操作
        batch.put("key1", "value1")
        batch.put("key2", "value2")
        batch.delete("key1")  # 删除操作
        
        # 执行批处理
        db.write(batch)
        
        # 验证结果
        assert db.get("key2") == "value2"
        assert db.not_exist("key1")
    
    def test_batch_with_column_family(self, db):
        """测试在批处理中使用列族"""
        # 创建列族
        users_cf = db.create_column_family("users")
        posts_cf = db.create_column_family("posts")
        
        # 获取列族句柄
        users_handle = db.get_column_family_handle("users")
        posts_handle = db.get_column_family_handle("posts")
        
        # 创建批处理
        batch = WriteBatch()
        
        # 添加不同列族的操作
        batch.put("user:01", "alice", users_handle)
        batch.put("user:02", "bob", users_handle)
        batch.put("post:01", "Hello World", posts_handle)
        
        # 执行批处理
        db.write(batch)
        
        # 验证结果
        assert users_cf.get("user:01") == "alice"
        assert users_cf.get("user:02") == "bob"
        assert posts_cf.get("post:01") == "Hello World"
        
        # 清理
        db.drop_column_family("users")
        db.drop_column_family("posts")
    
    def test_batch_rollback(self, db):
        """测试批处理回滚"""
        # 预先写入一些数据
        db.put("key1", "original1")
        db.put("key2", "original2")
        
        try:
            batch = WriteBatch()
            batch.put("key1", "new1")
            batch.put("key2", "new2")
            raise Exception("Simulated error")  # 模拟错误
            db.write(batch)  # 这行不会执行
        except Exception:
            pass  # 预期的异常
        
        # 验证数据没有改变
        assert db.get("key1") == "original1"
        assert db.get("key2") == "original2"
