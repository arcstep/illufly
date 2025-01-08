import pytest
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Dict, Union
from illufly.io.rocksdict.index import IndexedRocksDB
import tempfile
import shutil

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    caplog.set_level(logging.INFO)

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path, logger=logger)
    try:
        yield db
    finally:
        db.close()

# 测试用的数据模型
class User(BaseModel):
    name: str
    age: int
    email: Optional[str] = None
    
class Post(BaseModel):
    title: str
    author: str
    tags: List[str]
    created_at: datetime
    metadata: Dict[str, str]

class TestBasicIndexOperations:
    """基础索引操作测试"""
    
    def test_register_simple_index(self, db):
        """测试注册简单字段索引"""
        db.register_indexes("user", User, "name")
        db.register_indexes("user", User, "age")
        
        # 验证索引元数据
        metadata = list(db.indexes_metadata_cf.items())
        assert len(metadata) == 2
        
    def test_basic_crud_with_index(self, db):
        """测试带索引的基本CRUD操作"""
        db.register_indexes("user", User, "name")
        
        # 创建
        user = User(name="alice", age=25)
        db.update_with_indexes("user", "user:1", user.model_dump())
        
        # 读取
        assert db.get("user:1") == user.model_dump()
        
        # 通过索引查询
        keys = list(db.iter_keys_with_indexes("user", "name", "alice"))
        assert len(keys) == 1
        assert keys[0] == "user:1"
        
        # 更新
        user.name = "alice2"
        db.update_with_indexes("user", "user:1", user.model_dump())
        keys = list(db.iter_keys_with_indexes("user", "name", "alice2"))
        assert len(keys) == 1
        
        # 删除
        db.delete_with_indexes("user", "user:1")
        keys = list(db.iter_keys_with_indexes("user", "name", "alice2"))
        assert len(keys) == 0

class TestComplexIndexOperations:
    """复杂索引操作测试"""
    
    def test_dict_field_index(self, db):
        post = {
            "title": "test",
            "author": "alice",
            "tags": ["python", "test"],
            "created_at": datetime.now(),
            "metadata": {"category": "tech"}
        }
        PostType = Dict[str, Union[
            str,                    # 用于 title 和 author
            List[str],             # 用于 tags
            datetime,              # 用于 created_at
            Dict[str, str]         # 用于 metadata
        ]]

        db.register_indexes("post", PostType, "metadata.category")
        db.update_with_indexes("post", "post:1", post)
        items = db.keys(prefix="idx", rdict=db.get_column_family(db.INDEX_CF))
        logger.info(f"index items: {items}")
        
        keys = list(db.iter_keys_with_indexes("post", "metadata.category", "tech"))
        logger.info(f"keys: {keys}")
        assert len(keys) == 1
        assert keys[0] == "post:1"

    def test_model_field_index(self, db):
        """测试嵌套字段索引"""
        post = Post(
            title="test",
            author="alice",
            tags=["python", "test"],
            created_at=datetime.now(),
            metadata={"category": "tech"}
        )
        
        db.register_indexes("post", Post, "metadata.category")
        db.update_with_indexes("post", "post:1", post.model_dump())
        
        keys = list(db.iter_keys_with_indexes("post", "metadata.category", "tech"))
        assert len(keys) == 1
        assert keys[0] == "post:1"

class TestRangeQueries:
    """范围查询测试"""
    
    @pytest.fixture
    def db_with_data(self, db_path):
        db = IndexedRocksDB(db_path)
        db.register_indexes("user", User, "age")
        
        # 插入测试数据
        for i in range(10):
            user = User(name=f"user{i}", age=20+i)
            db.update_with_indexes("user", f"user:{i}", user.model_dump())
            
        try:
            yield db
        finally:
            db.close()
    
    def test_range_query(self, db_with_data):
        """测试范围查询"""
        # 查询年龄在 22-25 之间的用户
        # 查询方法遵循左闭右开的原则
        keys = list(db_with_data.iter_keys_with_indexes(
            "user", "age", 
            start=22, 
            end=26
        ))
        assert len(keys) == 4
        
        # 反向查询
        keys_reverse = list(db_with_data.iter_keys_with_indexes(
            "user", "age", 
            start=26, 
            end=22, 
            reverse=True
        ))
        assert len(keys_reverse) == 4
        assert sorted(keys_reverse) == sorted(keys)

class TestSpecialCases:
    """特殊情况测试"""
    
    @pytest.fixture
    def db(self, db_path):
        db = IndexedRocksDB(db_path)
        try:
            yield db
        finally:
            db.close()
    
    def test_null_values(self, db):
        """测试空值索引"""
        db.register_indexes("user", User, "email")
        
        user1 = User(name="alice", age=25)  # email is None
        user2 = User(name="bob", age=30, email="bob@example.com")
        
        db.update_with_indexes("user", "user:1", user1.model_dump())
        db.update_with_indexes("user", "user:2", user2.model_dump())
        
        # 查询 email 为空的用户
        keys = list(db.iter_keys_with_indexes("user", "email", None))
        assert len(keys) == 1
        assert keys[0] == "user:1"
    
    def test_special_characters(self, db):
        """测试特殊字符处理"""
        db.register_indexes("user", User, "name")
        
        user = User(name="test:user.with/special*chars", age=25)
        db.update_with_indexes("user", "user:1", user.model_dump())
        
        keys = list(db.iter_keys_with_indexes(
            "user", "name", "test:user.with/special*chars"
        ))
        assert len(keys) == 1
        assert keys[0] == "user:1" 