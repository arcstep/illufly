import pytest
from pathlib import Path
from illufly.fastapi.agents.vectordb.manager import VectorDBManager

@pytest.fixture
def vector_db_manager(users_manager, temp_dir):
    """创建测试用的向量库管理器"""
    manager = VectorDBManager(users_manager=users_manager)
    return manager

@pytest.fixture
def test_db_config():
    """测试用的数据库配置"""
    return {}

def test_create_db(vector_db_manager, exist_user, test_db_config):
    """测试创建向量库"""
    result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        db_config=test_db_config,
    )
    
    assert result.success, f"创建向量库失败: {result.error}"
    assert result.data.instance is not None

def test_create_duplicate_db(vector_db_manager, exist_user, test_db_config):
    """测试创建重复的向量库"""
    # 首先创建一个数据库
    first_result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        db_config=test_db_config,
    )
    assert first_result.success
    
    # 尝试创建同名数据库
    result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        db_config=test_db_config,
    )
    
    assert not result.success
    assert "already exists" in result.error

def test_list_dbs(vector_db_manager, exist_user, test_db_config):
    """测试列出用户的向量库"""
    # 创建测试数据库
    db1_result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db1",
        db_config=test_db_config,
    )
    assert db1_result.success
    
    db2_result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db2",
        db_config=test_db_config,
    )
    assert db2_result.success
    
    result = vector_db_manager.list_dbs(
        user_id=exist_user.user_id,
    )
    
    assert result.success
    dbs = result.data
    assert len(dbs) == 2
    assert "test_db1" in dbs
    assert "test_db2" in dbs

def test_get_db(vector_db_manager, exist_user, test_db_config):
    """测试获取向量库实例"""
    # 创建测试数据库
    create_result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        db_config=test_db_config,
    )
    assert create_result.success
    
    result = vector_db_manager.get_db(
        user_id=exist_user.user_id,
        db_name="test_db",
    )
    
    assert result.success, f"获取向量库失败: {result.error}"
    assert result.data.instance is not None

def test_remove_db(vector_db_manager, exist_user, test_db_config):
    """测试删除向量库"""
    # 创建测试数据库
    create_result = vector_db_manager.create_db(
        user_id=exist_user.user_id,
        db_name="test_db",
        db_config=test_db_config,
    )
    assert create_result.success
    
    result = vector_db_manager.remove_db(
        user_id=exist_user.user_id,
        db_name="test_db",
    )
    
    assert result.success, f"删除向量库失败: {result.error}"
    
    # 验证数据库已被删除
    list_result = vector_db_manager.list_dbs(
        user_id=exist_user.user_id,
    )
    assert list_result.success
    assert "test_db" not in list_result.data