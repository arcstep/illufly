import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from illufly.io.huang_index.index import IndexableRocksDB

import logging

# 只为特定模块设置日志级别
logging.getLogger(__name__).setLevel(logging.INFO)
logger = logging.getLogger(__name__)

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
        db = IndexableRocksDB(db_path, logger=logger)  # 集合已在初始化时创建
        yield db
        db.close()
        
    @pytest.fixture
    def indexed_db(self, db):
        """创建带索引配置的数据库实例"""
        # 注册索引
        db.register_model_index(dict, "{email}")  # 使用 dict 而不是 Dict
        db.register_model_index(dict, "{age}")
        db.register_model_index(dict, "{vip}")
        return db

    def test_index_registration(self, db):
        """测试索引注册"""
        # 先注册索引
        db.register_model_index(dict, "{email}")
        
        # 然后验证索引配置
        assert "{email}" in db.index_manager._model_indexes[dict]

    def test_key_validation(self, indexed_db):
        """测试键验证"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试包含 :key: 的键
        with pytest.raises(ValueError, match=r".*包含保留的关键标识符.*"):
            db.set("users", "user:key:1", {
                "name": "test",
                "email": "test@example.com"
            })
        
        # 测试其他包含冒号的键是允许的
        db.set("users", "user:with:colon", {
            "name": "test",
            "email": "test@example.com"
        })
        
        # 测试值中包含冒号是允许的
        db.set("users", "user:1", {
            "name": "test:with:colon",
            "email": "test:example:com"
        }) 

    def test_base_crud_operations(self, db):
        """测试基本的CRUD操作是否正常"""
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }

        db.set_collection_options("users", {"compression_type": "lz4"})
        
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

    def test_index_auto_update(self, indexed_db):
        """测试索引自动更新"""
        db = indexed_db
        collection = "users"
        key = "user:1"
        
        # 准备测试数据
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }
        
        # 预期的索引格式
        def make_expected_indexes(email, age, vip):
            """生成预期的索引格式"""
            indexes = [
                f"idx:users:{{email}}:{email}:key:user:1",
                f"idx:users:{{age}}:{age}:key:user:1",
                f"idx:users:{{vip}}:{vip}:key:user:1"
            ]
            reverse_indexes = [
                f"rev:users:{{email}}:{email}:idx:users:{{email}}:{email}:key:user:1",
                f"rev:users:{{age}}:{age}:idx:users:{{age}}:{age}:key:user:1",
                f"rev:users:{{vip}}:{vip}:idx:users:{{vip}}:{vip}:key:user:1"
            ]
            return indexes, reverse_indexes
        
        db.set_collection_options(collection, {"compression_type": "lz4"})
        
        # 1. 创建记录并验证索引
        db.set(collection, key, user)
        initial_indexes, initial_reverse_indexes = make_expected_indexes("zhangsan@example.com", 30, True)
        
        # 验证索引创建
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"创建后的正向索引: {all_indexes}")
        logger.info(f"创建后的反向索引: {all_reverse_indexes}")
        
        for idx in initial_indexes:
            assert idx in all_indexes, f"索引未创建: {idx}"
        for rev_idx in initial_reverse_indexes:
            assert rev_idx in all_reverse_indexes, f"反向索引未创建: {rev_idx}"
        
        # 2. 更新记录
        user["email"] = "zhangsan_new@example.com"
        user["age"] = 31
        db.set(collection, key, user)
        
        # 新的预期索引
        updated_indexes, updated_reverse_indexes = make_expected_indexes("zhangsan_new@example.com", 31, True)
        
        # 验证索引更新
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"更新后的正向索引: {all_indexes}")
        logger.info(f"更新后的反向索引: {all_reverse_indexes}")
        
        # 验证旧索引已删除
        for idx in initial_indexes:
            if idx not in updated_indexes:  # 只检查应该被删除的索引
                assert idx not in all_indexes, f"旧索引未删除: {idx}"
        
        # 验证新索引已创建
        for idx in updated_indexes:
            assert idx in all_indexes, f"新索引未创建: {idx}"
        for rev_idx in updated_reverse_indexes:
            assert rev_idx in all_reverse_indexes, f"新反向索引未创建: {rev_idx}"
        
        # 3. 删除记录
        db.delete(collection, key)
        
        # 验证索引清理
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"删除后的正向索引: {all_indexes}")
        logger.info(f"删除后的反向索引: {all_reverse_indexes}")
        
        for idx in updated_indexes:
            assert idx not in all_indexes, f"索引未被清理: {idx}"
        for rev_idx in updated_reverse_indexes:
            assert rev_idx not in all_reverse_indexes, f"反向索引未被清理: {rev_idx}"

    def test_index_query(self, indexed_db):
        """测试索引查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备测试数据
        users = [
            {"name": "张三", "email": "zhangsan@example.com", "age": 30, "vip": True},
            {"name": "李四", "email": "lisi@example.com", "age": 25, "vip": False},
            {"name": "王五", "email": "wangwu@example.com", "age": 35, "vip": True}
        ]
        
        # 先打印已注册的索引
        logger.info(f"已注册的索引: {db.index_manager._model_indexes}")
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
            
        # 打印创建的索引
        logger.info(f"正向索引: {list(db.all_indexes('users'))}")
        logger.info(f"反向索引: {list(db.all_reverse_indexes('users'))}")
        
        # 测试精确查询 - 使用花括号
        results = list(db.all("users", field_path="{email}", field_value="zhangsan@example.com"))
        assert len(results) == 1, f"email 查询结果: {results}"
        assert results[0][1]["name"] == "张三"
        
        # 测试范围查询 - 使用花括号
        results = list(db.all("users", field_path="{age}", field_value=30))
        assert len(results) == 1, f"age 查询结果: {results}"
        assert results[0][1]["name"] == "张三"
        
        # 测试布尔值查询 - 使用花括号
        results = list(db.all("users", field_path="{vip}", field_value=True))
        assert len(results) == 2, f"vip 查询结果: {results}"
        assert {r[1]["name"] for r in results} == {"张三", "王五"}
        
        # 测试 first/last - 使用花括号
        first_vip = db.first("users", field_path="{vip}", field_value=True)
        assert first_vip[1]["name"] == "张三", f"first_vip 结果: {first_vip}"
        
        last_vip = db.last("users", field_path="{vip}", field_value=True)
        assert last_vip[1]["name"] == "王五", f"last_vip 结果: {last_vip}"

    def test_range_query(self, indexed_db):
        """测试范围查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备测试数据
        users = [
            {"name": "张三", "email": "zhangsan@example.com", "age": 30, "score": 85.5},
            {"name": "李四", "email": "lisi@example.com", "age": 25, "score": 92.0},
            {"name": "王五", "email": "wangwu@example.com", "age": 35, "score": 78.5},
            {"name": "赵六", "email": "zhaoliu@example.com", "age": 28, "score": 88.0},
            {"name": "钱七", "email": "qianqi@example.com", "age": 32, "score": 95.5}
        ]
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
        
        # 测试年龄范围查询
        results = list(db.all("users", field_path="{age}", start=28, end=32))
        assert len(results) == 3, f"age 范围查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"张三", "赵六", "钱七"}, f"查询到的用户: {names}"
        
        # 测试分数范围查询（浮点数）
        results = list(db.all("users", field_path="{score}", start=85.0, end=93.0))
        assert len(results) == 3, f"score 范围查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"张三", "李四", "赵六"}, f"查询到的用户: {names}"
        
        # 测试只有起始值的范围查询
        results = list(db.all("users", field_path="{age}", start=32))
        assert len(results) == 2, f"age >= 32 查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"王五", "钱七"}, f"查询到的用户: {names}"
        
        # 测试只有结束值的范围查询
        results = list(db.all("users", field_path="{score}", end=80.0))
        assert len(results) == 1, f"score <= 80.0 查询结果: {results}"
        assert results[0][1]["name"] == "王五"
        
        # 测试范围查询的排序
        results = list(db.all("users", field_path="{age}", start=25, end=35))
        ages = [r[1]["age"] for r in results]
        assert ages == sorted(ages), f"年龄排序不正确: {ages}"
        
        # 测试反向范围查询
        results = list(db.all("users", field_path="{age}", start=25, end=35, reverse=True))
        ages = [r[1]["age"] for r in results]
        assert ages == sorted(ages, reverse=True), f"反向年龄排序不正确: {ages}"
        
        # 测试 first/last 与范围查询结合
        first_result = db.first("users", field_path="{age}", start=28, end=32)
        assert first_result[1]["age"] == 28, f"范围内第一个结果不正确: {first_result}"
        
        last_result = db.last("users", field_path="{age}", start=28, end=32)
        assert last_result[1]["age"] == 32, f"范围内最后一个结果不正确: {last_result}" 