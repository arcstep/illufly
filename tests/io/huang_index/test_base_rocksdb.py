import pytest
import tempfile
import shutil
from pathlib import Path
from rocksdict import Options
from illufly.io.huang_index import BaseRocksDB

# 配置日志
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture
def db_path():
    """创建临时数据库目录"""
    temp_dir = tempfile.mkdtemp()
    logger.info(f"Created temp db path: {temp_dir}")
    yield temp_dir
    shutil.rmtree(temp_dir)
    
@pytest.fixture
def db(db_path):
    """创建数据库实例"""
    db = BaseRocksDB(db_path, logger=logger)
    db.set_collection_options("users", {})
    yield db
    db.close()

@pytest.fixture
def custom_system_options():
    """自定义系统列族配置"""
    return {
        "write_buffer_size": 64 * 1024 * 1024,
        "max_write_buffer_number": 3,
        "min_write_buffer_number_to_merge": 1
    }

@pytest.fixture
def meta_collections():
    """预定义的元数据列族配置"""
    return {
        "indexes": {
            "write_buffer_size": 32 * 1024 * 1024,
            "compression_type": "lz4"
        },
        "models": {
            "write_buffer_size": 16 * 1024 * 1024,
            "compression_type": "zstd"
        }
    }

class TestRocksDBBasic:
    """测试 RocksDB 基础操作"""
    
    def test_db_init(self, db_path):
        """测试数据库初始化"""
        db = BaseRocksDB(db_path)
        try:
            assert Path(db_path).exists()
            assert "default" in db.list_collections()
        finally:
            db.close()

    def test_collection_operations(self, db):
        """测试集合的创建、列举和删除"""
        # 创建自定义集合
        db.set_collection_options("test_collection", {
            'write_buffer_size': 64 * 1024 * 1024,
            'compression_type': 'lz4'
        })
        
        # 验证集合创建
        collections = db.list_collections()
        assert "test_collection" in collections
        
        # 删除集合
        db.drop_collection("test_collection")
        assert "test_collection" not in db.list_collections()

    def test_crud_operations(self, db):
        """测试基本的增删改查操作"""
        test_data = {"name": "张三", "age": 30}
        
        # 设置值
        db.set("users", "user:123", test_data)
        
        # 获取值
        value = db.get("users", "user:123")
        assert value == test_data
        
        # 更新值
        updated_data = {**test_data, "email": "zhangsan@example.com"}
        db.set("users", "user:123", updated_data)
        value = db.get("users", "user:123")
        assert value == updated_data
        
        # 删除值
        db.delete("users", "user:123")
        assert db.get("users", "user:123") is None

class TestRocksDBIteration:
    """测试 RocksDB 迭代器功能"""
    
    @pytest.fixture
    def db_with_data(self, db):
        """准备带有测试数据的数据库"""
        test_data = {
            "user:1": {"name": "用户1"},
            "user:2": {"name": "用户2"},
            "user:3": {"name": "用户3"},
            "user:4": {"name": "用户4"},
            "user:5": {"name": "用户5"}
        }
        for k, v in test_data.items():
            db.set("users", k, v)
        return db

    def test_iteration(self, db_with_data):
        """测试键的迭代和范围查询"""
        # 测试前缀迭代
        keys = list(db_with_data.iter_keys("users", prefix="user:"))
        assert len(keys) == 5
        assert all(k.startswith("user:") for k in keys)
        
        # 测试不同的区间类型
        # 1. 闭区间 [user:2, user:4]
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="[]"))
        assert len(keys) == 3
        assert "user:2" in keys
        assert "user:3" in keys
        assert "user:4" in keys
        
        # 2. 左闭右开区间 [user:2, user:4)
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="[)"))
        assert len(keys) == 2
        assert "user:2" in keys
        assert "user:3" in keys
        assert "user:4" not in keys
        
        # 3. 左开右闭区间 (user:2, user:4]
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="(]"))
        assert len(keys) == 2
        assert "user:2" not in keys
        assert "user:3" in keys
        assert "user:4" in keys
        
        # 4. 开区间 (user:2, user:4)
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="()"))
        assert len(keys) == 1
        assert "user:2" not in keys
        assert "user:3" in keys
        assert "user:4" not in keys
        
        # 测试反向迭代
        # 1. 闭区间 [user:2, user:4] 反向
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="[]", reverse=True))
        assert len(keys) == 3
        assert keys == ["user:4", "user:3", "user:2"]
        
        # 2. 左闭右开区间 [user:2, user:4) 反向
        keys = list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="[)", reverse=True))
        assert len(keys) == 2
        assert keys == ["user:3", "user:2"]
        
        # 测试限制数量
        keys = list(db_with_data.iter_keys("users", prefix="user:", limit=2))
        assert len(keys) == 2
        
        # 测试无效的区间类型
        with pytest.raises(ValueError, match="无效的区间类型"):
            list(db_with_data.iter_keys("users", start="user:2", end="user:4", range_type="<>"))

    def test_first_last(self, db_with_data):
        """测试获取首条和末条记录"""
        # 测试首条记录
        first = db_with_data.first("users")
        assert first is not None
        first_key, first_value = first
        assert first_key == "user:1"
        assert first_value["name"] == "用户1"
        
        # 测试末条记录
        last = db_with_data.last("users")
        assert last is not None
        last_key, last_value = last
        assert last_key == "user:5"
        assert last_value["name"] == "用户5"

    def test_all_method(self, db_with_data):
        """测试 all 方法"""
        # 测试基本功能 - 默认限制
        results = db_with_data.all("users")
        assert len(results) == 5
        assert dict(results) == {
            "user:1": {"name": "用户1"},
            "user:2": {"name": "用户2"},
            "user:3": {"name": "用户3"},
            "user:4": {"name": "用户4"},
            "user:5": {"name": "用户5"}
        }
        
        # 测试限制条数
        limited_results = db_with_data.all("users", limit=3)
        assert len(limited_results) == 3
        assert all(k in {"user:1", "user:2", "user:3"} for k, v in limited_results)
        
        # 测试空集合
        with pytest.raises(ValueError) as e:
            db_with_data.all("non_existent_collection")
        assert "不存在" in str(e.value)
        
        # 测试超出最大限制
        with pytest.raises(ValueError, match=f"返回条数限制不能超过 {db_with_data.MAX_ITEMS_LIMIT}"):
            db_with_data.all("users", limit=db_with_data.MAX_ITEMS_LIMIT + 1)
        
        # 测试大量数据
        # 写入接近最大限制的数据量
        db_with_data.set_collection_options("large_users", {})
        large_data = {
            f"large:user:{i}": {"name": f"用户{i}"} 
            for i in range(db_with_data.MAX_ITEMS_LIMIT - 100)  # 留出一些余量
        }
        
        for key, value in large_data.items():
            db_with_data.set("large_users", key, value)
            
        # 测试接近最大限制的查询
        large_results = db_with_data.all("large_users", limit=db_with_data.MAX_ITEMS_LIMIT)
        assert len(large_results) == len(large_data)
        
        # 测试无限制查询
        unlimited_results = db_with_data.all("users", limit=None)
        assert len(unlimited_results) == 5
        assert dict(unlimited_results) == {
            "user:1": {"name": "用户1"},
            "user:2": {"name": "用户2"},
            "user:3": {"name": "用户3"},
            "user:4": {"name": "用户4"},
            "user:5": {"name": "用户5"}
        }

class TestRocksDBBatch:
    """测试 RocksDB 批处理功能"""

    def test_batch_write(self, db):
        """测试批量写入操作"""
        # 准备测试数据
        test_data = {
            "user:1": {"name": "用户1", "age": 20},
            "user:2": {"name": "用户2", "age": 30},
            "user:3": {"name": "用户3", "age": 40}
        }
        
        # 使用批量写入
        with db.batch_write() as batch:
            for key, value in test_data.items():
                db.set("users", key, value)
                
        # 验证数据写入
        for key, expected_value in test_data.items():
            value = db.get("users", key)
            assert value == expected_value
            
    def test_batch_write_rollback(self, db):
        """测试批量写入的回滚"""
        # 写入初始数据
        db.set("users", "user:1", {"name": "用户1"})
        
        # 模拟批量写入过程中的错误
        try:
            with db.batch_write() as batch:
                db.set("users", "user:2", {"name": "用户2"})
                db.delete("users", "user:1")
                raise ValueError("模拟错误")
        except ValueError:
            pass
            
        # 验证数据未被修改
        assert db.get("users", "user:1") == {"name": "用户1"}
        assert db.get("users", "user:2") is None
        
    def test_batch_write_multiple_collections(self, db):
        """测试跨集合的批量写入"""
        # 准备不同集合的测试数据
        db.set_collection_options("products", {})
        
        test_data = {
            "users": {
                "user:1": {"name": "用户1"},
                "user:2": {"name": "用户2"}
            },
            "products": {
                "prod:1": {"name": "产品1"},
                "prod:2": {"name": "产品2"}
            }
        }
        
        # 批量写入多个集合
        with db.batch_write() as batch:
            for collection, items in test_data.items():
                for key, value in items.items():
                    db.set(collection, key, value)
                    
        # 验证所有集合的数据
        for collection, items in test_data.items():
            for key, expected_value in items.items():
                value = db.get(collection, key)
                assert value == expected_value
                
    def test_batch_write_large_batch(self, db):
        """测试大批量写入"""
        # 准备大量测试数据
        test_data = {
            f"user:{i}": {"name": f"用户{i}", "data": "x" * 1000}
            for i in range(1000)  # 1000条记录
        }
        
        # 批量写入
        with db.batch_write() as batch:
            for key, value in test_data.items():
                db.set("users", key, value)
                
        # 验证数据总量
        count = sum(1 for _ in db.iter_keys("users", prefix="user:"))
        assert count == 1000
        
        # 随机验证几条数据
        import random
        for _ in range(10):
            i = random.randint(1, 1000)
            key = f"user:{i}"
            assert db.get("users", key) == test_data[key]

class TestRocksDBStats:
    """测试 RocksDB 统计功能"""

    def test_statistics(self, db):
        """测试数据库统计信息"""
        # 写入一些测试数据
        for i in range(100):
            db.set("users", f"user:{i}", {"name": f"用户{i}", "data": "x" * 1000})
            
        # 获取统计信息
        stats = db.get_statistics()
        
        # 基本统计
        assert "disk_usage" in stats
        assert "num_entries" in stats
        assert stats["num_entries"] >= 100
        
        # 列族统计
        assert "collections" in stats
        assert "users" in stats["collections"]
        assert stats["collections"]["users"]["num_entries"] >= 100
        assert "options" in stats["collections"]["users"]
        
        # 缓存统计
        assert "cache" in stats
        cache_stats = stats["cache"]
        assert "block_cache" in cache_stats
        assert "row_cache" in cache_stats
        assert cache_stats["block_cache"]["capacity"] > 0
        assert cache_stats["row_cache"]["capacity"] > 0
        
        # 写缓冲区统计
        assert "write_buffer" in stats
        write_buffer_stats = stats["write_buffer"]
        assert write_buffer_stats["buffer_size"] > 0
        assert "usage" in write_buffer_stats
        assert "enabled" in write_buffer_stats

class TestRocksDBInit:
    """测试 RocksDB 初始化相关功能"""
    
    def test_init_with_system_options(self, db_path, custom_system_options):
        """测试使用自定义系统选项初始化"""
        db = BaseRocksDB(db_path, system_options=custom_system_options)
        try:
            system_options = db.get_collection_options(BaseRocksDB.SYSTEM_CF)
            for key, value in custom_system_options.items():
                assert system_options[key] == value
        finally:
            db.close()

    def test_init_with_meta_collections(self, db_path, meta_collections):
        """测试使用预定义元数据列族初始化"""
        db = BaseRocksDB(db_path, collections=meta_collections)
        try:
            collections = db.list_collections()
            for cf_name in meta_collections:
                assert cf_name in collections
                options = db.get_collection_options(cf_name)
                for key, value in meta_collections[cf_name].items():
                    assert options[key] == value
        finally:
            db.close()

    def test_combined_init(self, db_path, custom_system_options, meta_collections):
        """测试同时使用系统选项和元数据列族初始化"""
        db = BaseRocksDB(
            db_path, 
            system_options=custom_system_options,
            collections=meta_collections
        )
        try:
            # 验证系统列族配置
            system_options = db.get_collection_options(BaseRocksDB.SYSTEM_CF)
            for key, value in custom_system_options.items():
                assert system_options[key] == value
                
            # 验证元数据列族配置
            for cf_name, expected_options in meta_collections.items():
                assert cf_name in db.list_collections()
                options = db.get_collection_options(cf_name)
                for key, value in expected_options.items():
                    assert options[key] == value
        finally:
            db.close()

class TestRocksDBMetaPersistence:
    """测试元数据持久化"""
    
    def test_meta_persistence(self, db_path, custom_system_options, meta_collections):
        """测试配置的持久化"""
        # 首次创建数据库
        db1 = BaseRocksDB(
            db_path,
            system_options=custom_system_options,
            collections=meta_collections
        )
        db1.close()
        
        # 重新打开数据库
        db2 = BaseRocksDB(db_path)
        try:
            # 验证系统列族配置保持不变
            system_options = db2.get_collection_options(BaseRocksDB.SYSTEM_CF)
            for key, value in custom_system_options.items():
                assert system_options[key] == value
                
            # 验证元数据列族配置保持不变
            for cf_name, expected_options in meta_collections.items():
                assert cf_name in db2.list_collections()
                options = db2.get_collection_options(cf_name)
                for key, value in expected_options.items():
                    assert options[key] == value
        finally:
            db2.close()

