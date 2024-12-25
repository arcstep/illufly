import pytest
from pathlib import Path
from datetime import datetime

from illufly.core.runnable.vectordb import VectorDB
from illufly.community.dashscope import TextEmbeddings
from illufly.community.faiss import FaissDB
from illufly.io import LocalFileKnowledgeDB
from illufly.fastapi.agents.vectordb.factory import BaseVectorDBFactory, DefaultVectorDBFactory
from illufly.fastapi.agents.vectordb.models import VectorDBConfig

class TestDefaultVectorDBFactory:
    """测试默认向量库工厂实现"""
    
    @pytest.fixture
    def factory(self):
        return DefaultVectorDBFactory()

    @pytest.fixture
    def db_name(self):
        return "test_db"

    @pytest.fixture
    def config(self, temp_dir, db_name):
        return VectorDBConfig(
            db_name=db_name,
            embeddings_config={
                "embeddings": "TextEmbeddings",
                "params": {}
            },
            knowledge_config={
                "knowledge": "LocalFileKnowledgeDB",
                "params": {"directory": Path(temp_dir) / "test_dir"}
            },
            vdb_config={
                "vdb": "FaissDB",
                "params": {
                    "top_k": 5,
                    "device": "cpu",
                    "batch_size": 1024
                }
            }
        )

    def test_create_db_instance(self, factory, config, setup_env, temp_dir, db_name ):
        """测试创建向量库实例"""
        # 设置临时存储路径
        instance = factory.create_db_instance(
            user_id="test_user",
            db_name=db_name,
            config=config
        )
        
        # 验证实例创建
        assert isinstance(instance, VectorDB)
        assert isinstance(instance, FaissDB)
        assert instance.name == db_name
        
        # 验证存储路径创建
        expected_path = Path(temp_dir) / "test_user" / "store" / db_name
        assert expected_path.exists()
        assert expected_path.is_dir()

    def test_create_db_instance_with_custom_config(self, factory, setup_env, set_env, db_name):
        """测试使用自定义配置创建向量库实例"""
        
        custom_config = VectorDBConfig(
            embeddings_config={
                "embeddings": "TextEmbeddings",
                "params": {"model": "custom_model"}
            },
            knowledge_config={
                "knowledge": "LocalFileKnowledgeDB",
                "params": {"directory": "custom_dir"}
            },
            vdb_config={
                "vdb": "FaissDB",
                "params": {
                    "top_k": 10,
                    "device": "cuda",
                    "batch_size": 2048
                }
            }
        )
        
        instance = factory.create_db_instance(
            user_id="test_user",
            db_name=db_name,
            config=custom_config
        )
        
        assert isinstance(instance, FaissDB)
        assert instance.name == db_name
        # 验证自定义参数是否正确应用
        assert instance.top_k == 10
        assert instance.device == "cuda"
        assert instance.batch_size == 2048

class TestCustomVectorDBFactory:
    """测试自定义向量库工厂实现"""

    @pytest.fixture
    def db_name(self):
        return "test_db"

    class CustomFactory(BaseVectorDBFactory):
        def create_db_instance(
            self,
            user_id: str,
            db_name: str,
            config: VectorDBConfig,
        ):
            return None
    
    def test_custom_factory_implementation(self, db_name):
        """测试自定义工厂实现"""
        factory = self.CustomFactory()
        result = factory.create_db_instance(
            user_id="test_user",
            db_name=db_name,
            config=VectorDBConfig()
        )
        assert result is None