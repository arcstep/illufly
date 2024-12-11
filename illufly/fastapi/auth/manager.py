from typing import Dict, Any, Optional, Set, Union, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Response
import re

from ...config import get_env
from ..common import StorageProtocol, FileStorage
from .dependencies import AuthDependencies

@dataclass
class Token:
    """令牌数据模型"""
    token: str
    username: str
    expire: datetime
    token_type: str  # "access" 或 "refresh"
    
    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "username": self.username,
            "expire": self.expire.isoformat(),
            "token_type": self.token_type
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Token':
        return Token(
            token=data["token"],
            username=data["username"],
            expire=datetime.fromisoformat(data["expire"]),
            token_type=data["token_type"]
        )
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expire

class AuthManager:
    def __init__(self, storage: Optional[StorageProtocol[Token]] = None, dependencies: Optional[AuthDependencies] = None):
        """初始化令牌管理器
        Args:
            storage: 令牌存储实现，如果为None则使用默认的文件存储
        """
        if storage is None:
            storage = FileStorage[Token](
                data_dir="__tokens__",
                filename="tokens.json",
                serializer=lambda token: token.to_dict(),
                deserializer=Token.from_dict,
                use_id_subdirs=True
            )
        self._storage = storage
        self._access_tokens: Dict[str, Token] = {}  # 内存中的访问令牌缓存
        
        # 添加新的属性
        self.secret_key = get_env("FASTAPI_SECRET_KEY")
        self.algorithm = get_env("FASTAPI_ALGORITHM")
        self.hash_method = get_env("HASH_METHOD")
        
        # 初始化密码加密上下文
        self.pwd_context = CryptContext(
            schemes=["argon2", "bcrypt", "pbkdf2_sha256"],
            default=self.hash_method,
            argon2__memory_cost=65536,
            argon2__time_cost=3,
            argon2__parallelism=4,
            bcrypt__rounds=12,
            pbkdf2_sha256__rounds=100000,
            truncate_error=True
        )
        
        # 创建依赖管理器
        self.dependencies = dependencies or AuthDependencies(self)
        
    @property
    def get_current_user(self):
        """获取当前用户依赖"""
        return self.dependencies.get_current_user
        
    def require_roles(self, roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
        """获取角色验证依赖"""
        return self.dependencies.require_roles(roles, require_all)

    def add_token(self, token: str, username: str, expire_time: timedelta, token_type: str) -> None:
        """添加令牌
        
        Args:
            token: 令牌字符串
            username: 用户名
            expire_time: 过期时间
            token_type: 令牌类型 ("access" 或 "refresh")
        """
        expire = datetime.utcnow() + expire_time
        token_obj = Token(
            token=token,
            username=username,
            expire=expire,
            token_type=token_type
        )
        
        if token_type == "access":
            self._clear_expired_access_tokens()
            self._access_tokens[token] = token_obj
        else:  # refresh token
            self._storage.set(token, token_obj, owner_id=username)
            
    def is_token_valid(self, token: str, token_type: str) -> bool:
        """检查令牌是否有效
        
        Args:
            token: 令牌字符串
            token_type: 令牌类型 ("access" 或 "refresh")
            
        Returns:
            bool: 令牌是否有效
        """
        if token_type == "access":
            if token in self._access_tokens:
                token_obj = self._access_tokens[token]
                if not token_obj.is_expired():
                    return True
                self._remove_access_token(token)
        else:  # refresh token
            for username in self._storage.list_owners():
                if stored_token := self._storage.get(token, owner_id=username):
                    if not stored_token.is_expired():
                        return True
                    # 删除过期令牌
                    self._storage.delete(token, owner_id=username)
        return False
        
    def remove_user_tokens(self, username: str) -> None:
        """移除用户的所有令牌"""
        # 移除访问令牌
        tokens_to_remove = [
            token for token, token_obj in self._access_tokens.items()
            if token_obj.username == username
        ]
        for token in tokens_to_remove:
            self._remove_access_token(token)
            
        # 移除刷新令牌
        if tokens := self._storage.list(owner_id=username):
            for token in tokens:
                self._storage.delete(token.token, owner_id=username)
                
    def _remove_access_token(self, token: str) -> None:
        """从内存缓存中移除访问令牌"""
        if token in self._access_tokens:
            self._access_tokens.pop(token)
            
    def _clear_expired_access_tokens(self) -> None:
        """清理过期的访问令牌"""
        expired_tokens = [
            token for token, token_obj in self._access_tokens.items()
            if token_obj.is_expired()
        ]
        for token in expired_tokens:
            self._remove_access_token(token)

    def verify_jwt(self, token: str):
        """验证JWT令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError:
            return None

    def create_refresh_token(self, data: dict) -> str:
        """创建刷新令牌"""
        expire_days = get_env("ACCESS_TOKEN_EXPIRE_DAYS")
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=expire_days)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # 使用现有的add_token方法替代原来的whitelist操作
        self.add_token(
            token=encoded_jwt,
            username=data.get('username') or data.get('sub'),
            expire_time=timedelta(days=expire_days),
            token_type="refresh"
        )
        return encoded_jwt

    def create_access_token(self, data: dict) -> str:
        """创建访问令牌"""
        expire_minutes = get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        
        # 使用现有的add_token方法替代原来的whitelist操作
        self.add_token(
            token=encoded_jwt,
            username=data.get('username') or data.get('sub'),
            expire_time=timedelta(minutes=expire_minutes),
            token_type="access"
        )
        return encoded_jwt

    def set_auth_cookies(self, response: Response, access_token: str = None, refresh_token: str = None) -> None:
        """设置认证Cookie"""
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

    def hash_password(self, password: str) -> str:
        """对密码进行哈希处理"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def validate_password(password: str) -> tuple[bool, Optional[str]]:
        """验证密码强度"""
        if len(password) < 8:
            return False, "密码长度必须至少为8个字符"
        if not re.search(r"[A-Z]", password):
            return False, "密码必须包含至少一个大写字母"
        if not re.search(r"[a-z]", password):
            return False, "密码必须包含至少一个小写字母"
        if not re.search(r"\d", password):
            return False, "密码必须包含至少一个数字"
        return True, None

    @staticmethod
    def validate_email(email: str) -> tuple[bool, Optional[str]]:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False, "邮箱格式无效"
        return True, None

    @staticmethod
    def validate_username(username: str) -> tuple[bool, Optional[str]]:
        """验证用户名格式"""
        if not username:
            return False, "用户名不能为空"
            
        if len(username) < 3 or len(username) > 32:
            return False, "用户名长度必须在3到32个字符之间"
            
        if not username[0].isalpha():
            return False, "用户名必须以字母开头"
            
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            return False, "用户名只能包含字母、数字和下划线"
            
        return True, None
