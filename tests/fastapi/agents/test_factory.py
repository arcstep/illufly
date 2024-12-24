import pytest
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from illufly.types import ChatAgent
from illufly.flow import ChatLearn
from illufly.core.runnable.vectordb import VectorDB
from illufly.fastapi.agents import BaseAgentFactory, DefaultAgentFactory, AgentConfig

class MockVectorDB(VectorDB):
    """测试用的向量库实现"""
    def __init__(self, name: str):
        self.name = name

class TestDefaultAgentFactory:
    """测试默认工厂实现"""
    
    @pytest.fixture
    def factory(self):
        return DefaultAgentFactory()
    
    @pytest.fixture
    def mock_vectordb(self):
        return MockVectorDB("test_db")
    
    def test_create_agent_config(self, factory, temp_dir, monkeypatch):
        """测试创建代理配置"""
        monkeypatch.setenv("ILLUFLY_FASTAPI_USERS_PATH", str(temp_dir))
        
        config = factory.create_agent_config(
            user_id="test_user",
            agent_type="chat",
            agent_name="test_agent",
            vectordbs=["test_db"],
            description="测试代理",
            config={"temperature": 0.7}
        )
        
        # 验证基本属性
        assert isinstance(config, AgentConfig)
        assert config.agent_name == "test_agent"
        assert config.agent_type == "chat"
        assert config.description == "测试代理"
        assert config.vectordbs == ["test_db"]
        assert config.config == {"temperature": 0.7}
        
        # 验证路径
        assert Path(config.events_history_path).exists()
        assert Path(config.memory_history_path).exists()
        
        # 验证时间戳
        assert isinstance(config.created_at, datetime)

    def test_create_chat_agent_instance(self, factory, mock_vectordb):
        """测试创建聊天代理实例"""
        config = AgentConfig(
            agent_name="test_chat",
            agent_type="chat",
            vectordbs=["test_db"],
            events_history_path="test_events",
            memory_history_path="test_memory",
            created_at=datetime.now(),
        )
        
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=config,
            vectordb_instances=[mock_vectordb]
        )
        
        assert instance is not None
        assert instance.name == "test_chat"
        assert isinstance(instance, ChatAgent)

    def test_create_learn_agent_instance(self, factory, mock_vectordb):
        """测试创建学习代理实例"""
        config = AgentConfig(
            agent_name="test_learn",
            agent_type="learn",
            vectordbs=["test_db"],
            events_history_path="test_events",
            memory_history_path="test_memory",
            created_at=datetime.now(),
        )
        
        instance = factory.create_agent_instance(
            user_id="test_user",
            agent_config=config,
            vectordb_instances=[mock_vectordb]
        )
        
        assert instance is not None
        assert instance.name == "test_learn"
        assert isinstance(instance, ChatLearn)

    def test_create_invalid_agent_instance(self, factory):
        """测试创建无效类型的代理实例"""
        config = AgentConfig(
            agent_name="test_invalid",
            agent_type="invalid_type",
            vectordbs=[],
            events_history_path="test_events",
            memory_history_path="test_memory",
            created_at=datetime.now(),
        )
        
        with pytest.raises(ValueError) as exc_info:
            factory.create_agent_instance(
                user_id="test_user",
                agent_config=config
            )
        assert "Unknown agent type" in str(exc_info.value)

class TestCustomAgentFactory:
    """测试自定义工厂实现"""
    
    class CustomFactory(BaseAgentFactory):
        """测试用的自定义工厂"""
        def create_agent_config(
            self,
            user_id: str,
            agent_type: str,
            agent_name: str,
            vectordbs: List[str] = None,
            **kwargs
        ) -> AgentConfig:
            return AgentConfig(
                agent_name=agent_name,
                agent_type=agent_type,
                vectordbs=vectordbs or [],
                created_at=datetime.now(),
            )

        def create_agent_instance(
            self,
            user_id: str,
            agent_config: AgentConfig,
            vectordb_instances: List[VectorDB] = None,
        ) -> Optional[VectorDB]:
            return None
    
    def test_custom_factory_implementation(self, temp_dir, monkeypatch):
        """测试自定义工厂实现"""
        monkeypatch.setenv("ILLUFLY_FASTAPI_USERS_PATH", str(temp_dir))
        
        factory = self.CustomFactory()
        config = factory.create_agent_config(
            user_id="test_user",
            agent_type="custom",
            agent_name="test_agent"
        )
        
        assert isinstance(config, AgentConfig)
        assert config.agent_type == "custom"