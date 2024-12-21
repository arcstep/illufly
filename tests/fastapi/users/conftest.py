from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from illufly.io import FileConfigStore
from illufly.fastapi.users import TokensManager, UsersManager, User, UserRole

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
def tokens_manager(temp_dir):
    """创建测试用的认证管理器"""
    manager = TokensManager(config_store_path=temp_dir)
    yield manager

    shutil.rmtree(temp_dir)

@pytest.fixture
def users_manager(temp_dir, tokens_manager):
    """创建测试用的用户管理器"""
    manager = UsersManager(config_store_path=temp_dir, tokens_manager=tokens_manager)
    yield manager
    
    shutil.rmtree(temp_dir)

@pytest.fixture
def test_user_password():
    return "TestPass123"

@pytest.fixture
def test_user():
    return User(
        user_id="test123",
        username="testuser",
        email="testuser@example.com",
        roles=[UserRole.USER],
        device_id="test_device_123",
        device_name="Test Device"
    )

@pytest.fixture
def device_info():
    """设备信息fixture"""
    return {
        "device_id": "test_device_123",
        "device_name": "Test Device"
    }

