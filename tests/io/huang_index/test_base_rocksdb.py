import pytest
import tempfile
import shutil
from pathlib import Path
from rocksdict import Options
from illufly.io.huang_index import (
    BaseRocksDB,
    KeyPattern
)

class TestRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建数据库实例"""
        db = BaseRocksDB(db_path)
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

    def test_key_pattern(self, db):
        """测试键模式构造和验证"""
        # 测试有效的键
        valid_keys = [
            "user:123",
            "user:123:profile",
            "index:name:123",
            "file:path/to/file:content",
            "index:name:123:20241231",
        ]
        for key in valid_keys:
            assert db.validate_key(key), f"键 {key} 应该有效"
        
        # 测试无效的键
        invalid_keys = [
            "123",
            "invalid::key",
            ":no_prefix",
            "no_id:",
            "index:name:123:20241231:20241231",
        ]
        for key in invalid_keys:
            assert not db.validate_key(key), f"键 {key} 应该无效"

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
        # 测试无效的键
        with pytest.raises(ValueError, match="非法键格式"):
            db.set("users", "invalid::key", {"data": "test"})
            
        # 测试重复创建已存在的集合
        db.set_collection_options("test_collection", {
            'write_buffer_size': 64 * 1024 * 1024
        })
        with pytest.raises(ValueError, match="集合.*已存在"):
            db.set_collection_options("test_collection", {})

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