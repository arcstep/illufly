import pytest
import tempfile
import shutil
from pathlib import Path
from rocksdict import Options
from illufly.io.huang_index import (
    RocksDB,
    KeyPattern,
    HuangIndexModel,
    RocksDBConfig,
    ModelRegistry
)

class TestRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        Path(temp_dir).mkdir(parents=True, exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建数据库实例"""
        db = RocksDB(db_path)  # 直接使用默认配置
        yield db
        db.close()

    def test_db_init(self, db_path):
        """测试数据库初始化"""
        db = RocksDB(db_path)
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
            "file:path/to/file:content"
        ]
        for key in valid_keys:
            assert db.validate_key(key), f"键 {key} 应该有效"
        
        # 测试无效的键
        invalid_keys = [
            "invalid::key",
            ":no_prefix",
            "no_id:",
            ""
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
            "user:3": {"name": "用户3"}
        }
        for k, v in test_data.items():
            db.set("users", k, v)
            
        # 测试前缀迭代
        keys = list(db.iter_keys("users", prefix="user:"))
        assert len(keys) == 3
        assert all(k.startswith("user:") for k in keys)
        
        # 测试范围迭代
        keys = list(db.iter_keys("users", start="user:1", end="user:2"))
        assert len(keys) == 2
        
        # 测试限制数量
        keys = list(db.iter_keys("users", prefix="user:", limit=2))
        assert len(keys) == 2

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
        """测试统计信息获取"""
        # 准备一些测试数据
        for i in range(5):
            db.set("users", f"user:{i}", {"name": f"用户{i}"})
        
        # 获取统计信息
        stats = db.get_statistics()
        assert isinstance(stats, dict)
        assert "disk_usage" in stats
        assert "num_entries" in stats
        assert stats["num_entries"] >= 5  # 至少包含我们插入的5条记录

    def test_model_serialization(self, db):
        """测试模型序列化和存储"""
        # 创建测试用户
        user_data = {"name": "张三", "age": 30}
        db.set("users", "user:123", user_data)
        
        # 测试基本数据存储和读取
        loaded_data = db.get("users", "user:123")
        assert loaded_data == user_data
        
        # 测试 Pydantic 模型
        class User(HuangIndexModel):
            __collection__ = "users"
            __namespace__ = "user"
            __key_pattern__ = KeyPattern.PREFIX_ID
            
            name: str
            age: int
            
        # 注册模型
        ModelRegistry.register(User)
        
        user = User(name="李四", age=25)
        db.set("users", user.key, user)
        
        # 测试模型读取 - 现在应该返回模型实例
        loaded_user = db.get("users", user.key)
        assert isinstance(loaded_user, User)  # 修改这里：期望是 User 实例而不是 dict
        assert loaded_user.name == "李四"
        assert loaded_user.age == 25
        
        # 测试模型数据完整性
        assert loaded_user.model_dump() == {
            "name": "李四",
            "age": 25,
            "id": loaded_user.id,  # 动态ID
            "infix": None,
            "suffix": loaded_user.suffix  # 动态时间戳
        }

    def test_config_management(self, db):
        """测试配置管理功能"""
        # 测试默认配置
        assert hasattr(db, '_config')
        assert isinstance(db._config, RocksDBConfig)
        
        # 测试自定义配置
        custom_options = {
            'write_buffer_size': 32 * 1024 * 1024,
            'compression_type': 'lz4',
            'max_write_buffer_number': 3
        }
        
        db.set_collection_options("custom_collection", custom_options)
        assert "custom_collection" in db.list_collections()
        
        # 测试配置应用
        test_data = {"test": "data"}
        db.set("custom_collection", "test:1", test_data)
        loaded_data = db.get("custom_collection", "test:1")
        assert loaded_data == test_data

    def test_key_pattern_validation(self, db):
        """测试键模式验证的扩展场景"""
        # 测试更多键模式
        complex_keys = [
            "user:org_123:456",  # PREFIX_INFIX_ID
            "user:org_123:456:profile",  # PREFIX_INFIX_ID_SUFFIX
            "index:name:users:zhang",  # PREFIX_INFIX_PATH_VALUE
        ]
        
        for key in complex_keys:
            assert db.validate_key(key), f"键 {key} 应该有效"
        
        # 测试边界情况
        edge_cases = [
            "a:b",  # 最短有效键
            "very_long_prefix:very_long_infix:very_long_id",  # 长键
        ]
        
        for key in edge_cases:
            assert db.validate_key(key), f"键 {key} 应该有效"

    def test_compression_options(self, db):
        """测试压缩选项"""
        # 测试不同压缩类型
        compression_types = ['none', 'snappy', 'lz4', 'zstd']
        
        for comp_type in compression_types:
            collection_name = f"test_compression_{comp_type}"
            db.set_collection_options(collection_name, {
                'compression_type': comp_type,
                'write_buffer_size': 64 * 1024 * 1024
            })
            
            # 写入测试数据
            test_data = {"test": "compression" * 100}  # 创建一些可压缩的数据
            db.set(collection_name, "test:1", test_data)
            
            # 验证数据完整性
            loaded_data = db.get(collection_name, "test:1")
            assert loaded_data == test_data