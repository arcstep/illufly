# features/environment.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from behave.model import Feature
from behave.runner import Context
from typing import Optional

from illufly.fastapi.users import UserRole, TokensManager, UsersManager
from illufly.fastapi.users.endpoints import create_users_endpoints
from illufly.fastapi.agents import AgentsManager
from illufly.fastapi.agents.endpoints import create_agents_endpoints
from illufly.io import TinyFileDB
from illufly.config import get_env

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
    # 设置临时测试目录
    temp_dir = os.path.join(get_env("ILLUFLY_TEMP_DIR"), "test_users")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    # 设置环境变量
    os.environ["ILLUFLY_CONFIG_STORE_DIR"] = temp_dir
    os.environ["ILLUFLY_TEMP_DIR"] = temp_dir

    users_manager = UsersManager()
    agents_manager = AgentsManager(users_manager=users_manager)

    # 设置 FastAPI 应用
    app = FastAPI()
    create_users_endpoints(app, users_manager=users_manager)
    create_agents_endpoints(app, agents_manager=agents_manager)

    context.client = TestClient(app)
    context.users_manager = users_manager
    context.tokens_manager = users_manager.tokens_manager
    context.agents_manager = agents_manager
    context.vectordb_manager = agents_manager.vectordb_manager
