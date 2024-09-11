# 假设使用简单的文件存储来持久化白名单令牌列表
import json
import os
from typing import Dict, Any
from fastapi import HTTPException, Depends
from datetime import datetime, timedelta
from ..config import get_env, get_folder_root

# 假设access_token有效期为1小时
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 内存中的access_token白名单
access_token_whitelist: Dict[str, Any] = {}

def add_access_token_to_whitelist(access_token, username, expire_minutes):
    """将access_token添加到内存白名单，并清理过期的access_token"""
    clear_expired_access_tokens()  # 清理过期的令牌
    expire_time = datetime.utcnow() + timedelta(minutes=expire_minutes)
    access_token_whitelist[access_token] = {
        "username": username,
        "expire": expire_time
    }

def remove_access_token_from_whitelist(user_info: str):
    """从内存白名单中移除用户的所有access_token"""
    tokens_to_remove = [token for token, details in access_token_whitelist.items() if details["username"] == user_info['username']]
    print('remove_access_token_from_whitelist:', user_info)
    for token in tokens_to_remove:
        print(token)
        access_token_whitelist.pop(token)

def is_access_token_in_whitelist(access_token):
    """检查access_token是否在内存白名单中"""
    if access_token in access_token_whitelist:
        # 检查是否过期
        if datetime.utcnow() > access_token_whitelist[access_token]["expire"]:
            # 如果过期，从白名单中移除
            remove_access_token_from_whitelist(access_token)
            return False
        return True
    return False

def clear_expired_access_tokens():
    """清理过期的access_token"""
    for token in list(access_token_whitelist.keys()):
        if datetime.utcnow() > access_token_whitelist[token]["expire"]:
            remove_access_token_from_whitelist(token)


def load_token_whitelist():
    """
    从文件加载白名单刷新令牌列表;
    现在每个令牌都包含username和expire信息"""
    try:
        path = os.path.join(get_folder_root(), get_env("FASTAPI_TOKEN_WHITELIST"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_token_whitelist(whitelist):
    """
    将白名单刷新令牌列表保存到文件，
    同时移除过期的令牌
    """
    # 移除过期的令牌
    current_time = datetime.utcnow()
    whitelist = {token: data for token, data in whitelist.items() if current_time <= datetime.fromisoformat(data["expire"])}
    path = os.path.join(get_folder_root(), get_env("FASTAPI_TOKEN_WHITELIST"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as file:
        json.dump(whitelist, file)

def is_refresh_token_in_whitelist(refresh_token):
    """
    检查刷新令牌是否在白名单中，
    并检查是否过期
    """
    whitelist = load_token_whitelist()
    if refresh_token in whitelist:
        # 检查是否过期
        if datetime.utcnow() > datetime.fromisoformat(whitelist[refresh_token]["expire"]):
            return False
        return True
    return False

def add_refresh_token_to_whitelist(refresh_token, username, expire_days):
    """
    将刷新令牌添加到白名单，
    包括username和expire信息
    """
    whitelist = load_token_whitelist()
    expire_time = datetime.utcnow() + timedelta(days=expire_days)
    whitelist[refresh_token] = {
        "username": username,
        "expire": expire_time.isoformat()
    }
    save_token_whitelist(whitelist)

def remove_refresh_token_from_whitelist(user_info: str):
    """从文件白名单中移除用户的所有refresh_token"""
    whitelist = load_token_whitelist()
    tokens_to_remove = [token for token, details in whitelist.items() if details["username"] == user_info['username']]
    
    # 遍历tokens_to_remove列表，从whitelist中删除这些token
    for token in tokens_to_remove:
        del whitelist[token]
    
    # 保存更新后的whitelist
    save_token_whitelist(whitelist)