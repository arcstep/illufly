from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Response
from ...config import get_env
from .whitelist import (
    add_refresh_token_to_whitelist,
    add_access_token_to_whitelist,
)
from passlib.context import CryptContext
import re
from typing import Optional

SECRET_KEY = get_env("FASTAPI_SECRET_KEY")
ALGORITHM = get_env("FASTAPI_ALGORITHM")
HASH_METHOD = get_env("HASH_METHOD")

# 密码加密上下文
pwd_context = CryptContext(
    # 按优先级排序的哈希方案
    schemes=["argon2", "bcrypt", "pbkdf2_sha256"],
    
    # 使用环境变量指定的算法
    default=HASH_METHOD,
    
    # argon2 的具体配置
    argon2__memory_cost=65536,  # 64MB
    argon2__time_cost=3,        # 3 次迭代
    argon2__parallelism=4,      # 4 个并行线程
    
    # bcrypt 配置
    bcrypt__rounds=12,          # 工作因子
    
    # pbkdf2_sha256 配置
    pbkdf2_sha256__rounds=100000,  # 迭代次数
    
    truncate_error=True  # 密码长度检查
)

def verify_jwt(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def create_refresh_token(data: dict):
    expire_days = get_env("ACCESS_TOKEN_EXPIRE_DAYS")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=expire_days)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_refresh_token_to_whitelist(encoded_jwt, data.get('username') or data.get('sub'), expire_days)
    return encoded_jwt

def create_access_token(data: dict):
    expire_minutes = get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    add_access_token_to_whitelist(encoded_jwt, data.get('username') or data.get('sub'), expire_minutes)
    return encoded_jwt

def set_auth_cookies(response: Response, access_token: str=None, refresh_token: str=None):
    if access_token:
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="Lax"
        )

    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="Lax"
        )

def hash_password(password: str) -> str:
    """
    对密码进行哈希处理，使用当前最强的可用算法
    """
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    返回: 验证是否通过
    """
    return pwd_context.verify(plain_password, hashed_password)

def validate_password(password: str) -> tuple[bool, Optional[str]]:
    """
    验证密码强度
    返回: (是否有效, 错误信息)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    return True, None

def validate_email(email: str) -> tuple[bool, Optional[str]]:
    """
    验证邮箱格式
    返回: (是否有效, 错误信息)
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    return True, None

def validate_username(username: str) -> tuple[bool, Optional[str]]:
    """
    验证用户名格式
    - 长度在3-32个字符之间
    - 只能包含字母、数字、下划线
    - 必须以字母开头
    
    返回: (是否有效, 错误信息)
    """
    if not username:
        return False, "Username is required"
        
    if len(username) < 3 or len(username) > 32:
        return False, "Username must be between 3 and 32 characters"
        
    if not username[0].isalpha():
        return False, "Username must start with a letter"
        
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
        return False, "Username can only contain letters, numbers, and underscores"
        
    return True, None
