from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from illufly.fastapi.common import FileConfigStore
from illufly.fastapi.auth import AuthManager
from illufly.fastapi.users import UsersManager, User, UserRole

import pytest
import tempfile
import shutil

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return tmp_path

@pytest.fixture
def auth_manager(temp_dir):
    """创建测试用的认证管理器"""
    manager = AuthManager(config_store_path=temp_dir)
    yield manager

@pytest.fixture
def users_manager(temp_dir, auth_manager):
    """创建测试用的用户管理器"""
    manager = UsersManager(config_store_path=temp_dir, auth_manager=auth_manager)
    yield manager
    
    shutil.rmtree(temp_dir)

@pytest.fixture
def test_user_password():
    return "TestPass123"

@pytest.fixture
def test_user(auth_manager, test_user_password):
    return User(
        user_id="test123",
        username="testuser",
        email="testuser@example.com",
        roles=[UserRole.USER]
    )

@pytest.fixture
def device_info():
    """设备信息fixture"""
    return {
        "device_id": "test_device_123",
        "device_name": "Test Device"
    }

