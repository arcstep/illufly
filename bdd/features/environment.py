# features/environment.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from illufly.fastapi.user.models import UserRole
from datetime import datetime
from illufly.fastapi.user.endpoints import create_user_endpoints
import json
from bdd.features.mocks.auth_manager import AuthManagerMockFactory
from bdd.features.mocks.user_manager import UserManagerMockFactory
from behave.model import Feature
from behave.runner import Context
from typing import Optional

class JSONEncoder(json.JSONEncoder):
    """自定义 JSON 编码器"""
    def default(self, obj):
        if isinstance(obj, bool):
            return str(obj).lower()
        if isinstance(obj, (UserRole, set)):
            return list(obj) if isinstance(obj, set) else obj.value
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def add_audit_log(context, action: str, user_id: str, details: dict, status: str = 'success'):
    """添加审计日志
    
    Args:
        context: Behave context对象
        action: 操作类型
        user_id: 用户ID
        details: 详细信息
        status: 操作状态
    """
    audit_log = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'user_id': user_id,
        'details': details,
        'status': status
    }
    context.storage['audit_logs'].append(audit_log)
    return audit_log

def find_audit_log(context, action: str, user_id: str, status: str = 'success') -> dict:
    """查找审计日志
    
    Args:
        context: Behave context对象
        action: 操作类型
        user_id: 用户ID
        status: 操作状态
        
    Returns:
        dict: 找到的日志记录，如果未找到返回None
    """
    for log in context.storage['audit_logs']:
        if (log['action'] == action and 
            log['user_id'] == user_id and 
            log['status'] == status):
            return log
    return None

def before_all(context: Context) -> None:
    """在所有测试开始前运行"""
    print("\n=== before_all ===")
    print("启动测试环境...")
    context.config.setup_logging()
    
    print(f"步骤文件路径: {context.config.paths}")

def before_feature(context: Context, feature: Feature) -> None:
    """每个功能开始前运行"""
    print("\n=== before_feature ===")
    print(f"Feature 文件: {feature.filename}")
    print(f"Feature 名称: {feature.name}")
    print(f"Feature 标签: {feature.tags}")

def before_scenario(context: Context, scenario) -> None:
    """每个场景开始前运行"""
    
    # 添加存储管理器
    context.storage = {
        'register_data': [],
        'users': [],
        'tokens': [],
        'audit_logs': [],
        'refresh_tokens': {},
        'access_tokens': {},
    }

    # 使用工厂创建mock对象
    context.auth_manager = AuthManagerMockFactory.create()
    context.user_manager = UserManagerMockFactory.create(context.storage)
    
    # 添加辅助方法到context
    context.add_audit_log = lambda *args, **kwargs: add_audit_log(context, *args, **kwargs)
    context.find_audit_log = lambda *args, **kwargs: find_audit_log(context, *args, **kwargs)
    
    # 添加令牌辅助方法
    context.create_test_token = lambda token_type, user_data: create_test_token(context, token_type, user_data)
    context.validate_token = validate_token
    
    # 设置 FastAPI 应用
    app = FastAPI()
    create_user_endpoints(
        app,
        user_manager=context.user_manager,
        auth_manager=context.auth_manager
    )
    context.client = TestClient(app)
    
    # 初始化设备令牌
    context.device_a_tokens = {}
    context.device_b_tokens = {}

def create_test_token(context, token_type: str, user_data: dict) -> str:
    """创建测试用的令牌
    
    Args:
        context: Behave context
        token_type: 令牌类型 ('refresh' 或 'access')
        user_data: 用户数据
        
    Returns:
        str: 生成的令牌
    """
    if token_type == 'refresh':
        token = context.auth_manager.create_refresh_token({
            'user_id': user_data['user_id'],
            'username': user_data['username'],
            'roles': user_data['roles']
        })
        context.storage['refresh_tokens'][token['token']] = {
            'user_id': user_data['user_id'],
            'created_at': datetime.now()
        }
        return token['token']
    else:
        token = context.auth_manager.create_access_token({
            'user_id': user_data['user_id'],
            'username': user_data['username'],
            'roles': user_data['roles']
        })
        context.storage['access_tokens'][token['token']] = {
            'user_id': user_data['user_id'],
            'created_at': datetime.now()
        }
        return token['token']

def validate_token(context, token: str, token_type: str) -> bool:
    """验证令牌有效性
    
    Args:
        context: Behave context
        token: 要验证的令牌
        token_type: 令牌类型 ('refresh' 或 'access')
        
    Returns:
        bool: 令牌是否有效
    """
    storage = context.storage['refresh_tokens' if token_type == 'refresh' else 'access_tokens']
    return token in storage
