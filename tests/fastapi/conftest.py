from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from illufly.io import FileConfigStore
from illufly.fastapi.users import TokensManager, UsersManager, User, UserRole
from illufly.config import get_env

import pytest
import tempfile
import shutil
import os

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

@pytest.fixture
def temp_dir(tmp_path):
    """创建临时目录"""
    return tmp_path

@pytest.fixture(autouse=True)
def setup_env(temp_dir, monkeypatch):
    """在所有测试前设置环境变量"""
    monkeypatch.setenv("ILLUFLY_CONFIG_STORE_DIR", str(temp_dir))
    monkeypatch.setenv("ILLUFLY_TEMP_DIR", str(temp_dir))
    return temp_dir

@pytest.fixture
def tokens_manager(setup_env):
    """创建测试用的认证管理器"""
    return TokensManager()

@pytest.fixture
def users_manager(tokens_manager):
    """创建测试用的用户管理器"""
    return UsersManager(tokens_manager=tokens_manager)

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
        password_hash="dummy_hash_for_testing"
    )

@pytest.fixture
def device_info():
    """设备信息fixture"""
    return {
        "device_id": "test_device_123",
    }

@pytest.fixture()
def exist_user(users_manager, test_user_password):
    """已存在的用户
    创建并返回一个已存在的用户对象，用于测试。
    """
    user = User(
        user_id="exist_user",
        username="exist_user",
        email="exist_user@example.com",
        roles=[UserRole.USER]
    )
    result = users_manager.create_user(
        user_id=user.user_id,
        email=user.email,
        username=user.username,
        password=test_user_password
    )
    assert result.success
    return user
