# features/environment.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from illufly.fastapi.user.models import UserRole
from datetime import datetime
from illufly.fastapi.user.endpoints import create_user_endpoints
import json
from bdd.features.mocks.auth_manager import AuthManagerMockFactory
from bdd.features.mocks.user_manager import UserManagerMockFactory

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

def before_all(context):
    """在所有测试开始前运行"""
    print("启动测试环境...")

def before_scenario(context, scenario):
    """每个场景开始前运行"""
    # 使用工厂创建mock对象
    context.auth_manager = AuthManagerMockFactory.create()
    context.user_manager = UserManagerMockFactory.create()
    
    # 保持对existing_users的引用以保证兼容性
    context.existing_users = context.user_manager._existing_users
    
    # 添加存储管理器
    context.storage = {
        'users': [],
        'tokens': [],
        'audit_logs': []
    }
    
    # 添加辅助方法到context
    context.add_audit_log = lambda *args, **kwargs: add_audit_log(context, *args, **kwargs)
    context.find_audit_log = lambda *args, **kwargs: find_audit_log(context, *args, **kwargs)
    
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
