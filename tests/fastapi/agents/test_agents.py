import pytest
from pathlib import Path
from illufly.fastapi.agents import VectorDBManager, AgentsManager, AgentConfig

@pytest.fixture
def exist_db_name():
    return "test_db1"

@pytest.fixture
def vector_db_manager(users_manager, temp_dir, exist_user, exist_db_name):
    """创建测试用的向量库管理器"""
    manager = VectorDBManager(users_manager=users_manager, config_store_path=temp_dir)
    manager.create_db(
        user_id=exist_user.user_id,
        db_name=exist_db_name,
        db_config={},
    )
    assert manager.get_db(exist_user.user_id, exist_db_name).success, "创建向量库失败"
    return manager

@pytest.fixture
def agents_manager(users_manager, vector_db_manager, temp_dir, exist_user):
    """创建测试用的代理管理器"""
    manager = AgentsManager(
        users_manager=users_manager,
        vectordb_manager=vector_db_manager,
        config_store_path=temp_dir
    )
    return manager

@pytest.fixture
def exist_db1(vector_db_manager, exist_user):
    """已存在的数据库"""
    vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db1",
        db_config={},
    )

@pytest.fixture
def test_agent_config():
    """测试用的代理配置"""
    return {
        "type": "fake",
        "vectordbs": ["test_db1"],
        "config": {}
    }

@pytest.fixture
def exist_agent1(agents_manager, exist_user, exist_db1):
    """已存在的代理"""
    agents_manager.create_agent(
        user_id=exist_user.user_id,
        agent_type="fake",
        agent_name="test_agent1",
        vectordbs=["test_db1"]
    )
    result = agents_manager.get_agent(exist_user.user_id, "test_agent1")
    assert result.success
    return result.data

@pytest.fixture
def exist_agent2(agents_manager, exist_user, exist_db1):
    """已存在的代理"""
    agents_manager.create_agent(
        user_id=exist_user.user_id,
        agent_type="fake",
        agent_name="test_agent2",
        vectordbs=["test_db1"]
    )
    result = agents_manager.get_agent(exist_user.user_id, "test_agent2")
    assert result.success
    return result.data

def test_create_agent(agents_manager, exist_user, exist_db1):
    """测试创建代理"""
    result = agents_manager.create_agent(
        user_id=exist_user.user_id,
        agent_type="fake",
        agent_name="test_agent_new",
        vectordbs=["test_db1"]
    )
    
    assert result.success, f"创建代理失败: {result.error}"
    assert result.data is not None
    assert isinstance(result.data, AgentConfig)

def test_create_duplicate_agent(agents_manager, exist_user, exist_agent1):
    """测试创建重复的代理"""
    result = agents_manager.create_agent(
        user_id=exist_user.user_id,
        agent_type="fake",
        agent_name=exist_agent1.name,
        vectordbs=["test_db1"]
    )
    
    assert not result.success
    assert "已存在" in result.error

def test_list_agents(agents_manager, exist_user, exist_agent1, exist_agent2):
    """测试列出用户的代理"""
    result = agents_manager.list_agents(
        user_id=exist_user.user_id,
    )
    
    assert result.success
    agents = result.data
    assert len(agents) == 2
    agent_names = [agent["agent_name"] for agent in agents]
    assert exist_agent1.name in agent_names
    assert exist_agent2.name in agent_names

def test_get_agent(agents_manager, exist_user, exist_agent1):
    """测试获取代理实例"""
    result = agents_manager.get_agent(
        user_id=exist_user.user_id,
        agent_name="test_agent1",
    )
    
    assert result.success, f"获取代理失败: {result.error}"
    assert result.data is not None

def test_get_nonexistent_agent(agents_manager, exist_user):
    """测试获取不存在的代理"""
    result = agents_manager.get_agent(
        user_id=exist_user.user_id,
        agent_name="nonexistent_agent",
    )
    
    assert not result.success
    assert "不存在" in result.error

def test_remove_agent(agents_manager, exist_user, exist_agent1):
    """测试删除代理"""
    result = agents_manager.remove_agent(
        user_id=exist_user.user_id,
        agent_name="test_agent1",
    )
    
    assert result.success, f"删除代理失败: {result.error}"
    
    # 验证代理已被删除
    list_result = agents_manager.list_agents(
        user_id=exist_user.user_id,
    )
    assert list_result.success
    agent_names = [agent["name"] for agent in list_result.data]
    assert "test_agent1" not in agent_names
