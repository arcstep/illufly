# features/environment.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from behave.model import Feature
from behave.runner import Context
from typing import Optional

from illufly.fastapi.user.models import UserRole
from illufly.fastapi.user.endpoints import create_user_endpoints
from illufly.fastapi.auth.manager import AuthManager
from illufly.fastapi.user.manager import UserManager
from illufly.fastapi.common import FileConfigStore

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

import json
import os
import shutil

def before_all(context: Context) -> None:
    """在所有测试开始前运行"""
    print("\n=== before_all ===")
    print("启动测试环境...")

def before_feature(context: Context, feature: Feature) -> None:
    """每个功能开始前运行"""
    print("\n=== before_feature ===")
    print(f"Feature 文件: {feature.filename}")
    print(f"Feature 名称: {feature.name}")
    print(f"Feature 标签: {feature.tags}")

def before_scenario(context: Context, scenario) -> None:
    """每个场景开始前运行"""
    __USERS_PATH__ = "/tmp/illufly/test_users"
    if os.path.exists(__USERS_PATH__):
        shutil.rmtree(__USERS_PATH__)

    auth_manager = AuthManager(config_store_path=__USERS_PATH__)
    user_manager = UserManager(auth_manager=auth_manager, config_store_path=__USERS_PATH__)
    
    # 设置 FastAPI 应用
    app = FastAPI()
    create_user_endpoints(
        app,
        user_manager=user_manager,
        auth_manager=auth_manager
    )

    context.client = TestClient(app)
    context.user_manager = user_manager
    context.auth_manager = auth_manager
