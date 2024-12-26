import pytest
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from illufly.core.runnable import Runnable
from illufly.core.runnable.vectordb import VectorDB
from illufly.chat import ChatQwen, FakeLLM
from illufly.flow import ChatLearn
from illufly.io import LocalFileEventsHistory, LocalFileMemoryHistory
from illufly.fastapi.agents import BaseAgentFactory, DefaultAgentFactory
from illufly.fastapi.agents import AgentConfig, VectorDBConfig
from illufly.fastapi.agents import VectorDBManager

@pytest.fixture
def vectordb_manager(users_manager, setup_env):
    """创建向量库管理器"""
    return VectorDBManager(users_manager=users_manager)

@pytest.fixture
def test_vectordb(vectordb_manager, exist_user):
    """创建测试用的向量库实例"""
    result = vectordb_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        vdb_config={
            "vdb": "FaissDB",
            "params": {
                "top_k": 5,
                "device": "cpu",
                "batch_size": 1024
            }
        },
        knowledge_config={
            "knowledge": "LocalFileKnowledgeDB",
            "params": {}
        },
        embeddings_config={
            "embeddings": "TextEmbeddings",
            "params": {}
        }
    )
    assert result.success
    return result.data

@pytest.fixture
def factory():
    """创建测试用的工厂实例"""
    return DefaultAgentFactory()

@pytest.fixture
def chat_config():
    """聊天代理配置"""
    return AgentConfig(
        agent_type="chat",
        agent_name="test_chat",
        config={}
    )

@pytest.fixture
def fake_config():
    """测试代理配置"""
    return AgentConfig(
        agent_type="fake",
        agent_name="test_fake",
        config={}
    )

@pytest.fixture
def learn_config():
    """学习代理配置"""
    return AgentConfig(
        agent_type="learn",
        agent_name="test_learn",
        config={}
    )

class TestDefaultAgentFactory:
    """测试默认Agent工厂实现"""

    def test_create_chat_agent(self, factory, chat_config, setup_env, test_vectordb):
        """测试创建聊天代理"""
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=chat_config,
            vectordb_instances=[test_vectordb]
        )
        
        assert isinstance(instance, ChatQwen)
        assert instance.name == "test_chat"
        assert len(instance.vectordbs) == 1
        assert isinstance(instance.events_history, LocalFileEventsHistory)
        assert isinstance(instance.memory_history, LocalFileMemoryHistory)
        
        # 验证向量库实例
        for vdb in instance.vectordbs:
            assert isinstance(vdb, VectorDB)
            assert vdb.name == "test_db"

    def test_create_fake_agent(self, factory, fake_config, setup_env):
        """测试创建测试代理"""
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=fake_config
        )
        
        assert isinstance(instance, FakeLLM)
        assert instance.name == "test_fake"
        assert isinstance(instance.events_history, LocalFileEventsHistory)
        assert isinstance(instance.memory_history, LocalFileMemoryHistory)

    def test_create_learn_agent(self, factory, learn_config, setup_env, test_vectordb):
        """测试创建学习代理"""
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=learn_config,
            vectordb_instances=[test_vectordb]
        )
        
        assert isinstance(instance, ChatLearn)
        assert instance.name == "test_learn"
        assert isinstance(instance.events_history, LocalFileEventsHistory)

    def test_create_invalid_agent_type(self, factory, setup_env):
        """测试创建无效的代理类型"""
        invalid_config = AgentConfig(
            agent_type="invalid",
            agent_name="test_invalid",
            config={}
        )
        
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=invalid_config
        )
        
        assert instance is None

    def test_create_agent_with_invalid_config(self, factory, setup_env):
        """测试使用无效配置创建代理"""
        invalid_config = AgentConfig(
            agent_type="chat",
            agent_name="test_chat",
            config={
                "invalid_param": "value"  # 无效的配置参数
            }
        )
        
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=invalid_config
        )
        
        assert instance is None

    def test_storage_paths(self, factory, chat_config, setup_env, temp_dir):
        """测试存储路径创建"""
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=chat_config
        )
        
        # 验证存储路径创建
        expected_events_path = Path(temp_dir) / "test_user" / "store" / "hist" / "test_chat"
        expected_memory_path = Path(temp_dir) / "test_user" / "store" / "memory" / "test_chat"
        
        assert expected_events_path.exists()
        assert expected_events_path.is_dir()
        assert expected_memory_path.exists()
        assert expected_memory_path.is_dir()

class TestCustomAgentFactory:
    """测试自定义Agent工厂实现"""

    class CustomFactory(BaseAgentFactory):
        def create_agent_instance(
            self,
            user_id: str,
            agent_config: AgentConfig,
            vectordb_instances: List[VectorDB] = None,
        ) -> Optional[Runnable]:
            return None
    
    def test_custom_factory_implementation(self):
        """测试自定义工厂实现"""
        factory = self.CustomFactory()
        config = AgentConfig(
            agent_type="custom",
            agent_name="test_custom",
            config={}
        )
        
        result = factory.create_agent_instance(
            user_id="test_user",
            agent_config=config
        )
        
        assert result is None