import pytest
from pathlib import Path
from illufly.fastapi.agents.vectordb.manager import VectorDBManager
from illufly.fastapi.agents.vectordb.models import VectorDBConfig

@pytest.fixture
def vector_db_manager(users_manager, setup_env):
    """创建测试用的向量库管理器"""
    manager = VectorDBManager(users_manager=users_manager)
    return manager

@pytest.fixture
def vdb_config():
    """向量库配置"""
    return {
        "vdb": "FaissDB",
        "params": {
            "top_k": 5,
            "device": "cpu",
            "batch_size": 1024
        }
    }

@pytest.fixture
def knowledge_config(temp_dir):
    """知识库配置"""
    return {
        "knowledge": "LocalFileKnowledgeDB",
        "params": {
            "directory": str(temp_dir / "test_dir")
        }
    }

@pytest.fixture
def embeddings_config():
    """向量模型配置"""
    return {
        "embeddings": "TextEmbeddings",
        "params": {}
    }

@pytest.fixture
def exist_db1(vector_db_manager, exist_user, vdb_config, knowledge_config, embeddings_config):
    """已存在的数据库1"""
    vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db1",
        vdb_config=vdb_config,
        knowledge_config=knowledge_config,
        embeddings_config=embeddings_config
    )

@pytest.fixture
def exist_db2(vector_db_manager, exist_user, vdb_config, knowledge_config, embeddings_config):
    """已存在的数据库2"""
    vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db2",
        vdb_config=vdb_config,
        knowledge_config=knowledge_config,
        embeddings_config=embeddings_config
    )

def test_create_db(vector_db_manager, exist_user, vdb_config, knowledge_config, embeddings_config):
    """测试创建向量库"""
    result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db_new",
        vdb_config=vdb_config,
        knowledge_config=knowledge_config,
        embeddings_config=embeddings_config
    )
    
    assert result.success, f"创建向量库失败: {result.error}"
    assert result.data is not None

def test_create_db_with_defaults(vector_db_manager, exist_user):
    """测试使用默认配置创建向量库"""
    result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db_defaults"
    )
    
    assert result.success, f"创建向量库失败: {result.error}"
    assert result.data is not None

def test_create_duplicate_db(
    vector_db_manager,
    exist_user,
    exist_db1,
    vdb_config,
    knowledge_config,
    embeddings_config,
):
    """测试创建重复的向量库"""
    result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db1",
        vdb_config=vdb_config,
        knowledge_config=knowledge_config,
        embeddings_config=embeddings_config
    )
    assert not result.success
    assert "已存在" in result.error

def test_list_dbs(vector_db_manager, exist_user, exist_db1, exist_db2):
    """测试列出用户的向量库"""
    result = vector_db_manager.list_dbs(
        user_id=exist_user.user_id,
    )
    
    assert result.success
    dbs = result.data
    assert len(dbs) == 2
    assert "test_db1" in dbs
    assert "test_db2" in dbs

def test_get_db(vector_db_manager, exist_user, exist_db1):
    """测试获取向量库实例"""
    result = vector_db_manager.get_db_instance(
        user_id=exist_user.user_id,
        db_name="test_db1",
    )
    
    assert result.success, f"获取向量库失败: {result.error}"
    assert result.data is not None

def test_update_db_config(vector_db_manager, exist_user, exist_db1):
    """测试更新向量库配置"""
    new_config = {
        "vdb_config": {
            "vdb": "FaissDB",
            "params": {
                "top_k": 10,
                "device": "cpu",
                "batch_size": 2048
            }
        }
    }

    result = vector_db_manager.update_db_config(
        user_id=exist_user.user_id,
        db_name="test_db1",
        updates=new_config
    )

    assert result.success, f"更新配置失败: {result.error}"

    # 验证配置已更新
    db_result = vector_db_manager.get_db_config(
        user_id=exist_user.user_id,
        db_name="test_db1"
    )
    assert db_result.success
    
    # 修正配置属性的访问路径
    assert db_result.data.vdb_config["params"]["top_k"] == 10
    # 可以添加其他参数的验证
    assert db_result.data.vdb_config["params"]["batch_size"] == 2048
    assert db_result.data.vdb_config["params"]["device"] == "cpu"
    assert db_result.data.vdb_config["vdb"] == "FaissDB"

def test_remove_db(vector_db_manager, exist_user, exist_db1):
    """测试删除向量库"""
    result = vector_db_manager.remove_db(
        user_id=exist_user.user_id,
        db_name="test_db1",
    )
    
    assert result.success, f"删除向量库失败: {result.error}"
    
    # 验证数据库已被删除
    list_result = vector_db_manager.list_dbs(
        user_id=exist_user.user_id,
    )
    assert list_result.success
    assert "test_db1" not in list_result.data