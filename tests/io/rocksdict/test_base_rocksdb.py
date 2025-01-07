import pytest
from rocksdict import Rdict, Options, ReadOptions
from illufly.io.rocksdict.base_rocksdb import BaseRocksDB
import tempfile
import os
import shutil
from typing import Union

# 配置日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestBaseRocksDB:
    @pytest.fixture(autouse=True)
    def setup_logging(self, caplog):
        """设置日志级别"""
        caplog.set_level(logging.INFO)

    @pytest.fixture
    def db_path(self):
        """创建临时数据库路径"""
        path = tempfile.mkdtemp()
        yield path
        shutil.rmtree(path)
    
    @pytest.fixture
    def db(self, db_path):
        """创建测试数据库实例"""
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
        items = list(populated_db.iter(opts))
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
    
    def test_exist_not_exist(self, populated_db):
        """测试键存在性检查"""
        # 测试存在的键
        exists, value = populated_db.exist("user:01")
        assert exists
        assert value == "alice"
        
        # 测试不存在的键
        exists, value = populated_db.exist("user:999")
        assert not exists
        assert value is None
        
        # 测试快速不存在检查
        assert populated_db.not_exist("user:999")
        assert not populated_db.not_exist("user:01")
    
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
