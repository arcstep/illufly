import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel

from illufly.io.huang_index import ModelRocksDB, KeyPattern

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
        """创建测试用户模型"""
        class User(BaseModel):
            name: str
            age: int
            
            # 使用 model_config 替代 Config 类
            model_config = {
                'json_schema_extra': {
                    'examples': [{'name': '张三', 'age': 30}]
                }
            }
            
            def __infix__(self) -> str:
                return f"age_{self.age}"
                
            def __suffix__(self) -> str:
                return datetime.now().strftime("%Y%m")
        return User
        
    def test_model_registration(self, db, user_model):
        """测试模型注册"""
        # 基本注册
        assert db.register_model(user_model)
        
        # 获取元数据
        metadata = db.get_model(model_id="User")
        assert metadata is not None
        assert metadata["model_id"] == "User"
        assert metadata["collection"] == "default"
        
        # 自定义注册
        assert db.register_model(
            user_model,
            model_id="CustomUser",
            collection="users",
            key_pattern=KeyPattern.PREFIX_INFIX_ID_SUFFIX
        )
        
        # 验证重复注册
        with pytest.raises(ValueError, match="模型.*已存在"):
            db.register_model(user_model)
            
        # 允许更新
        assert db.register_model(user_model, allow_update=True)
    
    def test_model_serialization(self, db, user_model):
        """测试模型序列化"""
        db.register_model(
            user_model,
            key_pattern=KeyPattern.PREFIX_INFIX_ID_SUFFIX
        )
        
        # 保存实例
        user = user_model(name="张三", age=30)
        key = db.save(user)
        
        # 验证存在性
        assert db.load(key, "User") is not None
        
        # 加载实例
        loaded_user = db.load(key, "User")
        assert isinstance(loaded_user, user_model)
        assert loaded_user.name == "张三"
        assert loaded_user.age == 30
        
        # 测试自定义键生成
        key = db.save(user, infix="vip")
        assert "vip" in key
        
        # 测试无效模型 - 创建一个未注册的模型类
        class UnregisteredModel(BaseModel):
            value: str
        
        # 使用未注册的模型类进行测试
        with pytest.raises(ValueError) as exc_info:
            db.save(UnregisteredModel(value="test"))
        assert "未注册" in str(exc_info.value)

    
    def test_model_listing(self, db, user_model):
        """测试模型列举"""
        # 创建 vip 集合
        db.set_collection_options("vip", {})
        
        # 注册多个模型
        db.register_model(user_model)
        db.register_model(user_model, model_id="VipUser", collection="vip")
        
        # 列出所有模型
        models = db.list_models()
        assert len(models) == 2
        assert "models:default:User" in models
        assert "models:vip:VipUser" in models
        
        # 按集合过滤
        vip_models = db.list_models(collection="vip")
        assert len(vip_models) == 1
        assert "models:vip:VipUser" in vip_models
    
    def test_key_generation(self, db, user_model):
        """测试键生成"""
        db.register_model(
            user_model,
            key_pattern=KeyPattern.PREFIX_INFIX_ID_SUFFIX
        )
        
        user = user_model(name="张三", age=30)
        
        # 基本键生成
        key = db.make_key(user)
        assert key.startswith("User:age_30:")
        assert KeyPattern.validate_key(key)
        
        # 自定义组件
        key = db.make_key(user, infix="vip", suffix="2024")
        assert "vip" in key
        assert key.endswith(":2024")
        assert KeyPattern.validate_key(key)
    
    def test_model_operations(self, db, user_model):
        """测试模型操作的完整流程"""
        # 创建集合
        db.set_collection_options("users", {})
        
        # 注册模型
        db.register_model(user_model, collection="users")
        
        # 创建和保存实例
        users = [
            user_model(name=f"用户{i}", age=20+i)
            for i in range(3)
        ]
        
        keys = []
        for user in users:
            key = db.save(user)
            keys.append(key)
            
        # 验证所有实例
        for i, key in enumerate(keys):
            loaded = db.load(key, "User")
            assert loaded.name == f"用户{i}"
            assert loaded.age == 20 + i
            
        # 测试集合操作
        assert "users" in db.list_collections()
        
        # 测试集合查询
        all_users = list(db.list_models(collection="users"))
        assert len(all_users) == 1
        
        # 测试获取所有记录
        all_records = dict(db.all(collection="users", prefix="User:"))
        assert len(all_records) == 3 
