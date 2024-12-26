import pytest
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

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
    def embeddings_config(self):
        return {
            "embeddings": "TextEmbeddings",
            "params": {}
        }

    @pytest.fixture
    def knowledge_config(self, temp_dir):
        return {
            "knowledge": "LocalFileKnowledgeDB",
            "params": {}
        }

    @pytest.fixture
    def vdb_config(self):
        return {
            "vdb": "FaissDB",
            "params": {
                "top_k": 5,
                "device": "cpu",
                "batch_size": 1024
            }
        }

    @pytest.fixture
    def config(self, db_name, embeddings_config, knowledge_config, vdb_config):
        return VectorDBConfig(
            db_name=db_name,
            embeddings_config=embeddings_config,
            knowledge_config=knowledge_config,
            vdb_config=vdb_config
        )

    def test_create_db_instance(self, factory, config, setup_env, temp_dir, db_name):
        """测试创建向量库实例"""
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

    def test_create_db_instance_with_custom_config(self, factory, setup_env, db_name):
        """测试使用自定义配置创建向量库实例"""
        custom_config = VectorDBConfig(
            db_name=db_name,
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
                    "device": "cpu",
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
        assert instance.top_k == 10
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
    
    def test_custom_factory_implementation(self, db_name, default_knowledge_config, default_embeddings_config):
        """测试自定义工厂实现"""
        factory = self.CustomFactory()
        config = VectorDBConfig(
            db_name=db_name,
            vdb_config={
                "vdb": "CustomDB",
                "params": {"custom_param": "value"}
            },
            knowledge_config=default_knowledge_config,
            embeddings_config=default_embeddings_config
        )
        # ... 其他测试代码

@pytest.fixture
def default_vdb_config(setup_env) -> Dict[str, Any]:
    """默认向量库配置"""
    return {
        "vdb": "FaissDB",
        "params": {
            "persist_directory": str(setup_env),
            "top_k": 5,
            "device": "cpu",
            "batch_size": 1024
        }
    }

@pytest.fixture
def default_knowledge_config() -> Dict[str, Any]:
    """默认知识库配置"""
    return {
        "knowledge": "LocalFileKnowledgeDB",
        "params": {}
    }

@pytest.fixture
def default_embeddings_config() -> Dict[str, Any]:
    """默认嵌入配置"""
    return {
        "embeddings": "TextEmbeddings",
        "params": {}
    }

@pytest.fixture
def vector_db_config(db_name, default_vdb_config, default_knowledge_config, default_embeddings_config) -> VectorDBConfig:
    """完整的向量库配置"""
    return VectorDBConfig(
        db_name=db_name,
        vdb_config=default_vdb_config,
        knowledge_config=default_knowledge_config,
        embeddings_config=default_embeddings_config
    )