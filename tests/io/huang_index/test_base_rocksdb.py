import pytest
import tempfile
import shutil
import logging
from pathlib import Path
from rocksdict import Options
from illufly.io.huang_index import BaseRocksDB

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TestRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp db path: {temp_dir}")
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建数据库实例"""
        db = BaseRocksDB(db_path, logger=logger)
        # 初始化测试需要的集合
        db.set_collection_options("users", {})
        yield db
        db.close()

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

    def test_iteration(self, db):
        """测试键的迭代和范围查询"""
        # 准备测试数据
        test_data = {
            "user:1": {"name": "用户1"},
            "user:2": {"name": "用户2"},
            "user:3": {"name": "用户3"},
            "user:4": {"name": "用户4"},
            "user:5": {"name": "用户5"}
        }
        for k, v in test_data.items():
            db.set("users", k, v)
            
        # 测试前缀迭代
        keys = list(db.iter_keys("users", prefix="user:"))
        assert len(keys) == 5
        assert all(k.startswith("user:") for k in keys)
        
        # 测试不同的区间类型
        # 1. 闭区间 [user:2, user:4]
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="[]"))
        assert len(keys) == 3
        assert "user:2" in keys
        assert "user:3" in keys
        assert "user:4" in keys
        
        # 2. 左闭右开区间 [user:2, user:4)
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="[)"))
        assert len(keys) == 2
        assert "user:2" in keys
        assert "user:3" in keys
        assert "user:4" not in keys
        
        # 3. 左开右闭区间 (user:2, user:4]
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="(]"))
        assert len(keys) == 2
        assert "user:2" not in keys
        assert "user:3" in keys
        assert "user:4" in keys
        
        # 4. 开区间 (user:2, user:4)
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="()"))
        assert len(keys) == 1
        assert "user:2" not in keys
        assert "user:3" in keys
        assert "user:4" not in keys
        
        # 测试反向迭代
        # 1. 闭区间 [user:2, user:4] 反向
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="[]", reverse=True))
        assert len(keys) == 3
        assert keys == ["user:4", "user:3", "user:2"]
        
        # 2. 左闭右开区间 [user:2, user:4) 反向
        keys = list(db.iter_keys("users", start="user:2", end="user:4", range_type="[)", reverse=True))
        assert len(keys) == 2
        assert keys == ["user:3", "user:2"]
        
        # 测试限制数量
        keys = list(db.iter_keys("users", prefix="user:", limit=2))
        assert len(keys) == 2
        
        # 测试无效的区间类型
        with pytest.raises(ValueError, match="无效的区间类型"):
            list(db.iter_keys("users", start="user:2", end="user:4", range_type="<>"))

    def test_first_last(self, db):
        """测试获取首条和末条记录"""
        # 准备测试数据
        test_data = {
            "user:1": {"name": "用户1"},
            "user:2": {"name": "用户2"}
        }
        for k, v in test_data.items():
            db.set("users", k, v)
        
        # 测试首条记录
        first = db.first("users")
        assert first is not None
        first_key, first_value = first
        assert first_key == "user:1"
        assert first_value["name"] == "用户1"
        
        # 测试末条记录
        last = db.last("users")
        assert last is not None
        last_key, last_value = last
        assert last_key == "user:2"
        assert last_value["name"] == "用户2"

    def test_error_handling(self, db):
        """测试错误处理"""
        # 测试重复创建已存在的集合
        db.set_collection_options("test_collection", {
            'write_buffer_size': 64 * 1024 * 1024
        })
        # 尝试重复创建同一个集合
        with pytest.raises(ValueError, match="集合.*已存在"):
            db.set_collection_options("test_collection", {
                'write_buffer_size': 32 * 1024 * 1024
            })

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

    def test_reopen_database(self, db_path):
        """测试数据库重新打开后的列族状态"""
        # 1. 首次打开数据库并创建列族
        db1 = BaseRocksDB(db_path)
        try:
            # 创建测试列族
            test_options = {
                'write_buffer_size': 64 * 1024 * 1024,
                'max_write_buffer_number': 3,
                'min_write_buffer_number': 1
            }
            db1.set_collection_options("test_collection", test_options)
            db1.set_collection_options("another_collection", {})
            
            # 写入一些测试数据
            db1.set("test_collection", "key1", {"name": "test1"})
            db1.set("another_collection", "key2", {"name": "test2"})
            
            # 获取已存在的列族列表
            collections1 = set(db1.list_collections())
            
        finally:
            db1.close()
            
        # 2. 重新打开数据库
        db2 = BaseRocksDB(db_path)
        try:
            # 验证列族是否正确恢复
            collections2 = set(db2.list_collections())
            assert collections2 == collections1, \
                f"重新打开后的列族列表不匹配: {collections2} != {collections1}"
            
            # 验证数据是否正确恢复
            value1 = db2.get("test_collection", "key1")
            assert value1 == {"name": "test1"}, \
                f"test_collection 中的数据不匹配: {value1}"
            
            value2 = db2.get("another_collection", "key2")
            assert value2 == {"name": "test2"}, \
                f"another_collection 中的数据不匹配: {value2}"
            
            # 验证可以继续写入新数据
            db2.set("test_collection", "key3", {"name": "test3"})
            assert db2.get("test_collection", "key3") == {"name": "test3"}, \
                "无法在重新打开后的数据库中写入新数据"
            
            # 验证可以创建新的列族
            db2.set_collection_options("new_collection", {})
            db2.set("new_collection", "key4", {"name": "test4"})
            assert db2.get("new_collection", "key4") == {"name": "test4"}, \
                "无法在重新打开后的数据库中创建新列族"
            
            # 验证 default 列族是否正确初始化
            assert "default" in collections2, \
                "default 列族未被正确初始化"
            
        finally:
            db2.close()
            
    def test_collection_persistence(self, db_path):
        """测试列族配置的持久化"""
        # 1. 首次打开数据库并设置列族配置
        db1 = BaseRocksDB(db_path)
        try:
            test_options = {
                'write_buffer_size': 64 * 1024 * 1024,
                'max_write_buffer_number': 3,
                'min_write_buffer_number': 1
            }
            db1.set_collection_options("test_collection", test_options)
            
            # 获取统计信息
            stats1 = db1.get_statistics()
            collection_config1 = stats1["collections"]["test_collection"]["options"]
            
        finally:
            db1.close()
            
        # 2. 重新打开数据库并验证配置
        db2 = BaseRocksDB(db_path)
        try:
            # 获取统计信息
            stats2 = db2.get_statistics()
            collection_config2 = stats2["collections"]["test_collection"]["options"]
            
            # 验证配置是否保持一致
            assert collection_config2 == collection_config1, \
                f"列族配置未正确持久化: \n{collection_config2} != \n{collection_config1}"
                
        finally:
            db2.close()

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
