import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel
from typing import List, Dict
import time
import logging

from illufly.io.huang_index import ModelRocksDB, KeyPattern, HuangIndexModel

logger = logging.getLogger(__name__)

class TestModelRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建数据库实例"""
        db = ModelRocksDB(db_path)
        yield db
        db.close()
    
    @pytest.fixture
    def user_model(self):
        """创建测试用户模型类"""
        class User(BaseModel):
            name: str
            age: int
            
            def __infix__(self) -> str:
                return f"age_{self.age}"
                
            def __suffix__(self) -> str:
                return datetime.now().strftime("%Y%m")
        return User
        
    def test_model_registration(self, db, user_model):
        """测试模型注册"""
        # 基本注册
        assert db.register_model(model_class=user_model)
        
        # 获取元数据
        metadata = db.get_model_meta(model_id="User")
        assert metadata is not None
        assert metadata["model_id"] == "User"
        assert metadata["collection"] == "default"
        
        # 自定义注册
        assert db.register_model(
            model_class=user_model,
            model_id="CustomUser",
            collection="users",
            key_pattern=KeyPattern.PREFIX_INFIX_ID_SUFFIX
        )
        
        # 验证重复注册
        with pytest.raises(ValueError, match="模型.*已存在"):
            db.register_model(model_class=user_model)
            
        # 允许更新
        assert db.register_model(model_class=user_model, allow_update=True)
    
    def test_model_listing(self, db, user_model):
        """测试模型列举"""
        # 创建 vip 集合
        db.set_collection_options("vip", {})
        
        # 注册多个模型
        db.register_model(model_class=user_model)
        db.register_model(
            model_class=user_model,
            model_id="VipUser",
            collection="vip"
        )
        
        # 列出所有模型
        models = db.list_models_meta()
        logger.info(f"models: {models}")
        assert len(models) == 2
        assert any("User" in key for key in models.keys())
        assert any("VipUser" in key for key in models.keys())

    def test_model_metadata_management(self, db):
        """测试模型元数据管理"""
        class TestModel(BaseModel):
            value: str
            
        # 注册模型
        db.register_model(model_class=TestModel)
        
        # 获取元数据
        metadata = db.get_model_meta(model_id="TestModel")
        assert metadata is not None
        assert metadata["model_id"] == "TestModel"
        
        # 更新元数据
        updates = {"description": "测试模型"}
        db.update_model_meta(
            model_id="TestModel",
            updates=updates
        )
        
        # 验证更新
        updated_metadata = db.get_model_meta(model_id="TestModel")
        assert updated_metadata["description"] == "测试模型"

    def test_model_inheritance(self, db):
        """测试继承模型的注册"""
        class BaseUser(BaseModel):
            name: str
        
        class ExtendedUser(BaseUser):
            age: int
        
        # 注册基类和派生类
        db.register_model(model_class=BaseUser)
        db.register_model(model_class=ExtendedUser)
        
        # 验证元数据
        base_meta = db.get_model_meta(model_id="BaseUser")
        extended_meta = db.get_model_meta(model_id="ExtendedUser")
        
        assert "name" in base_meta["fields"]
        assert "name" in extended_meta["fields"]
        assert "age" in extended_meta["fields"]
        assert "age" not in base_meta["fields"]

    def test_model_registration_validation(self, db):
        """测试模型注册的验证"""
        # 测试无效的模型类
        with pytest.raises(ValueError):
            db.register_model(model_class=None)
            
        # 测试无效的键模式
        class TestModel(BaseModel):
            value: str
            
        with pytest.raises(ValueError):
            db.register_model(
                model_class=TestModel,
                key_pattern="invalid_pattern"
            )

    def test_model_same_path(self, db, user_model):
        """测试模型在同一数据库路径下的注册"""
        assert db.register_model(model_class=user_model)
        db.close()
        
        db_same_path = ModelRocksDB(db._db_path)
        meta = db_same_path.get_model_meta(model_id="User")
        assert meta is not None
        assert meta["model_id"] == "User"
        assert "name" in meta["fields"]
        assert "age" in meta["fields"]
        db_same_path.close()
