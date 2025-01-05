import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from illufly.io.huang_index.index import IndexableRocksDB

class TestIndexableRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建可索引数据库实例"""
        db = IndexableRocksDB(db_path)
        yield db
        db.close()
        
    @pytest.fixture
    def indexed_db(self, db):
        """创建带索引配置的数据库实例"""
        # 注册索引
        db.register_model_index(Dict, "email", "exact")
        db.register_model_index(Dict, "age", "range")
        db.register_model_index(Dict, "vip", "exact")
        return db

    def test_base_crud_operations(self, db):
        """测试基本的CRUD操作是否正常"""
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }
        
        # 创建
        db.set("users", "user:1", user)
        
        # 读取
        saved_user = db.get("users", "user:1")
        assert saved_user == user
        
        # 更新
        user["age"] = 31
        db.set("users", "user:1", user)
        updated_user = db.get("users", "user:1")
        assert updated_user["age"] == 31
        
        # 删除
        db.delete("users", "user:1")
        assert db.get("users", "user:1") is None

    def test_index_registration(self, db):
        """测试索引注册"""
        # 注册索引
        db.register_model_index(Dict, "email", "exact")
        db.register_model_index(Dict, "age", "range")
        
        # 验证索引配置
        assert "email" in db.index_manager._model_indexes[Dict]
        assert "age" in db.index_manager._model_indexes[Dict]
        assert db.index_manager._model_indexes[Dict]["email"] == "exact"
        assert db.index_manager._model_indexes[Dict]["age"] == "range"

    def test_index_auto_update(self, indexed_db):
        """测试索引自动更新"""
        db = indexed_db
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }
        
        # 创建时的索引
        db.set("users", "user:1", user)
        
        # 验证正向索引
        assert list(db.iter_keys("indexes", prefix=f"idx:users:email:zhangsan@example.com"))
        assert list(db.iter_keys("indexes", prefix=f"idx:users:age:000000030"))
        assert list(db.iter_keys("indexes", prefix=f"idx:users:vip:True"))
        
        # 验证反向索引
        reverse_index = db.get("reverse", f"rev:user:1:idx")
        assert reverse_index["fields"]["email"] == "zhangsan@example.com"
        assert reverse_index["fields"]["age"] == 30
        assert reverse_index["fields"]["vip"] is True
        
        # 更新时的索引
        user["email"] = "zhangsan_new@example.com"
        user["age"] = 31
        db.set("users", "user:1", user)
        
        # 验证旧索引已删除
        assert not list(db.iter_keys("indexes", prefix=f"idx:users:email:zhangsan@example.com"))
        assert not list(db.iter_keys("indexes", prefix=f"idx:users:age:000000030"))
        
        # 验证新索引已创建
        assert list(db.iter_keys("indexes", prefix=f"idx:users:email:zhangsan_new@example.com"))
        assert list(db.iter_keys("indexes", prefix=f"idx:users:age:000000031"))
        
        # 删除时的索引清理
        db.delete("users", "user:1")
        
        # 验证所有索引都已清理
        assert not list(db.iter_keys("indexes", prefix=f"idx:users:email:zhangsan_new@example.com"))
        assert not list(db.iter_keys("indexes", prefix=f"idx:users:age:000000031"))
        assert not list(db.iter_keys("indexes", prefix=f"idx:users:vip:True"))
        assert db.get("reverse", f"rev:user:1:idx") is None

    def test_index_query(self, indexed_db):
        """测试索引查询"""
        db = indexed_db
        
        # 准备测试数据
        users = [
            {"name": "张三", "email": "zhangsan@example.com", "age": 30, "vip": True},
            {"name": "李四", "email": "lisi@example.com", "age": 25, "vip": False},
            {"name": "王五", "email": "wangwu@example.com", "age": 35, "vip": True}
        ]
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
            
        # 测试精确查询
        results = list(db.all("users", field_path="email", field_value="zhangsan@example.com"))
        assert len(results) == 1
        assert results[0][1]["name"] == "张三"
        
        # 测试范围查询
        results = list(db.all("users", field_path="age", field_value=30))
        assert len(results) == 1
        assert results[0][1]["name"] == "张三"
        
        # 测试布尔值查询
        results = list(db.all("users", field_path="vip", field_value=True))
        assert len(results) == 2
        assert {r[1]["name"] for r in results} == {"张三", "王五"}
        
        # 测试 first/last
        first_vip = db.first("users", field_path="vip", field_value=True)
        assert first_vip[1]["name"] == "张三"
        
        last_vip = db.last("users", field_path="vip", field_value=True)
        assert last_vip[1]["name"] == "王五"

    def test_error_handling(self, indexed_db):
        """测试错误处理"""
        db = indexed_db
        
        # 测试非法键
        with pytest.raises(ValueError):
            db.set("users", "invalid::key", {
                "name": "测试",
                "email": "test@example.com",
                "age": 20
            }) 