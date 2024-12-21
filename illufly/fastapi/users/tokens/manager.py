from typing import Dict, Any, Optional, Set, Union, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Response
from pathlib import Path
from calendar import timegm

import re
import uuid
import os

from ....io import ConfigStoreProtocol, FileConfigStore
from ..dependencies import AuthDependencies

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

@dataclass
class TokensManager:
    """认证管理器，用于处理用户认证、令牌管理和多设备登录等功能。
    
    该类提供了完整的用户认证和令牌管理解决方案，包括：
    - JWT令牌的创建和验证
    - 多设备登录支持
    - 令牌撤销和过期管理
    - 密码加密和验证
    - 用户输入验证
    
    主要特性：
    - 支持访问令牌和刷新令牌
    - 支持多设备同时登录
    - 支持单个设备登出
    - 支持令牌自动过期
    - 支持密码强度验证
    - 支持用户名和邮箱格式验证
    
    使用示例:
    ```python
    # 初始化认证管理器
    auth_manager = TokensManager()
    
    # 创建访问令牌
    token_data = {
        "user_id": "user123",
        "username": "johndoe",
        "roles": ["user"]
    }
    access_token = auth_manager.create_access_token(token_data)
    
    # 设备登出
    auth_manager.logout_device(access_token["token"])
    ```
    
    配置要求：
    必须在环境变量中设置以下配置：
    - FASTAPI_SECRET_KEY: JWT签名密钥
    - FASTAPI_ALGORITHM: JWT算法 (HS256, HS384, HS512)
    - HASH_METHOD: 密码哈希方法 (argon2, bcrypt, pbkdf2_sha256)
    - ACCESS_TOKEN_EXPIRE_MINUTES: 访问令牌过期时间（分钟）
    - REFRESH_TOKEN_EXPIRE_DAYS: 刷新令牌过期时间（天）
    - ILLUFLY_FASTAPI_USERS_PATH: 用户数据存储路径
    
    安全注意事项：
    1. 访问令牌应该设置较短的过期时间（如30分钟）
    2. 刷新令牌可以设置较长的过期时间（如7天）
    3. 密码必须经过哈希处理后再存储
    4. 敏感操作应该验证用户角色权限
    """
    
    def __init__(self, storage: Optional[ConfigStoreProtocol] = None, config_store_path: str = None):
        """初始化认证管理器
        
        Args:
            storage: 可选的令牌存储实现，默认使用文件存储
            
        Raises:
            ValueError: 如果必要的环境变量未正确配置
        """
        # 验证必要的环境变量
        self.secret_key = get_env("FASTAPI_SECRET_KEY")
        if not self.secret_key:
            raise ValueError("FASTAPI_SECRET_KEY must be properly configured")
            
        self.algorithm = get_env("FASTAPI_ALGORITHM")
        if self.algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported JWT algorithm: {self.algorithm}")
            
        self.hash_method = get_env("HASH_METHOD")
        if self.hash_method not in ["argon2", "bcrypt", "pbkdf2_sha256"]:
            raise ValueError(f"Unsupported hash method: {self.hash_method}")
        
        # 初始化存储
        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(config_store_path or __USERS_PATH__),
                filename="tokens.json",
                data_class=Dict[str, Dict[str, Dict[str, Any]]]
            )
        self._refresh_tokens = storage
        self._access_tokens: Dict[str, Token] = {}
        
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
        self.dependencies = AuthDependencies(self)
        
        # 令牌过期时间配置
        self.access_token_expire_minutes = int(get_env("ACCESS_TOKEN_EXPIRE_MINUTES"))
        self.refresh_token_expire_days = int(get_env("REFRESH_TOKEN_EXPIRE_DAYS"))
        
    @property
    def get_current_user(self):
        """获取当前用户依赖"""
        return self.dependencies.get_current_user
        
    def require_roles(self, roles: Union["UserRole", List["UserRole"]], require_all: bool = False):
        """获取角色认证依赖"""
        return self.dependencies.require_roles(roles, require_all)

    def add_access_token(self, claims: dict, token: str, owner_id: str) -> None:
        """添加访问令牌，同时清理过期的令牌"""
        try:
            device_id = claims.get("device_id")
            if not device_id:
                raise ValueError("Device ID is required")
            
            # 获取用户当前的所有令牌
            current_time = int(datetime.utcnow().timestamp())
            user_tokens = self._access_tokens.get(owner_id, {})
            
            # 过滤出未过期的令牌
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in user_tokens.items()
                if token_data["claims"]["exp"] > current_time
            }
            
            # 添加新令牌
            valid_tokens[device_id] = {"claims": claims, "token": token}
            self._access_tokens[owner_id] = valid_tokens
            
        except Exception as e:
            raise

    def add_refresh_token(self, claims: dict, token: str, owner_id: str) -> None:
        """添加刷新令牌，同时清理过期的令牌"""
        try:
            device_id = claims.get("device_id")
            if not device_id:
                raise ValueError("Device ID is required")
            
            # 获取用户当前的所有令牌
            current_time = int(datetime.utcnow().timestamp())
            refresh_data = self._refresh_tokens.get(owner_id) or {}
            
            # 过滤出未过期的令牌
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in refresh_data.items()
                if token_data["claims"]["exp"] > current_time
            }
            
            # 添加新令牌
            valid_tokens[device_id] = {"claims": claims, "token": token}
            self._refresh_tokens.set(value=valid_tokens, owner_id=owner_id)
            
        except Exception as e:
            raise

    def verify_jwt(self, token: str, verify_exp: bool = True, token_type: str = None) -> Dict[str, Any]:
        """验证JWT令牌，如果是访问令牌且验证失败，尝试使用刷新令牌刷新
        
        Args:
            token: JWT令牌字符串
            verify_exp: 是否验证过期时间
            token_type: 令牌类型 ("access" 或 "refresh")
            
        Returns:
            Dict[str, Any]: 验证结果
                - success: 是否验证成功
                - payload: 成功时返回的令牌载荷
                - new_token: 如果刷新成功，返回新的访问令牌
                - error: 失败时的错误信息
        """
        try:
            # 先不验证签名解码看看内容
            unverified = jwt.decode(
                token,
                key=None,
                options={"verify_signature": False}
            )
            
            # 设置验证选项
            options = {
                'verify_signature': True,
                'verify_exp': verify_exp,
                'verify_iat': True,
                'require_exp': True,
                'require_iat': True,
                'leeway': 0,
            }
            
            # 正式验证
            try:
                payload = jwt.decode(
                    token,
                    key=self.secret_key,
                    algorithms=[self.algorithm],
                    options=options
                )
                
                # 检查令牌是否被撤销
                user_id = payload.get("user_id")
                if token_type == "access":
                    if self.is_access_token_revoked(token, user_id):
                        raise jwt.JWTError("Token has been revoked")
                elif token_type == "refresh":
                    if self.is_refresh_token_revoked(token, user_id):
                        raise jwt.JWTError("Token has been revoked")
                
                return {
                    "success": True,
                    "payload": payload
                }
                
            except (jwt.ExpiredSignatureError, jwt.JWTError) as e:
                # 如果是访问令牌验证失败，尝试使用刷新令牌
                if token_type == "access":
                    user_id = unverified.get("user_id")
                    device_id = unverified.get("device_id")
                    
                    # 查找相同设备的刷新令牌
                    refresh_data = self._refresh_tokens.get(user_id) or {}
                    device_tokens = refresh_data.get(device_id, {})
                    refresh_token = device_tokens.get("token")
                    
                    if refresh_token:
                        # 尝试刷新访问令牌
                        refresh_result = self.refresh_access_token(refresh_token, user_id)
                        if refresh_result["success"]:
                            return {
                                "success": True,
                                "payload": unverified,
                                "new_token": refresh_result["token"]
                            }
                
                return {
                    "success": False,
                    "error": f"Invalid token: {str(e)}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Token verification error: {str(e)}"
            }

    def create_refresh_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建刷新令牌
        
        Args:
            data: 同 create_access_token
                
        Returns:
            dict: 包含创建结果的字典
                - success: 是否成功
                - token: 成功时返回的令牌
                - error: 失败时的错误信息
        """
        try:
            device_id = data.get("device_id", "default")
            device_name = data.get("device_name", "Default Device")
            
            current_time = datetime.utcnow()
            expire = current_time + timedelta(days=self.refresh_token_expire_days)
            
            # 用 timegm 获取时间戳
            iat_timestamp = timegm(current_time.utctimetuple())
            exp_timestamp = timegm(expire.utctimetuple())
            
            claims = {
                **data,
                "exp": exp_timestamp,  # 使用 timegm 生成的时间戳
                "iat": iat_timestamp,  # 使用 timegm 生成的时间戳
                "token_type": "refresh",
                "device_id": device_id,
                "device_name": device_name
            }
            
            encoded_jwt = jwt.encode(
                claims,
                self.secret_key,
                algorithm=self.algorithm
            )
            
            # 使用 add_token 方法来管理令牌
            self.add_token(claims, token=encoded_jwt, owner_id=data["user_id"])
            
            return {
                "success": True,
                "token": encoded_jwt
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create refresh token: {str(e)}"
            }

    def create_access_token(self, data: dict) -> dict:
        """创建访问令牌"""
        try:
            device_id = data.get("device_id", "default")
            device_name = data.get("device_name", "Default Device")
            
            current_time = datetime.utcnow()
            expire = current_time + timedelta(minutes=self.access_token_expire_minutes)
            
            print(f"Creating token at: {current_time}")
            print(f"Token will expire at: {expire}")
            
            # 使用 timegm 获取时间戳
            iat_timestamp = timegm(current_time.utctimetuple())
            exp_timestamp = timegm(expire.utctimetuple())
            
            print(f"IAT timestamp: {iat_timestamp}")
            print(f"EXP timestamp: {exp_timestamp}")
            
            claims = {
                **data,
                "exp": exp_timestamp,  # 使用 timegm 生成的时间戳
                "iat": iat_timestamp,  # 使用 timegm 生成的时间戳
                "token_type": "access",
                "device_id": device_id,
                "device_name": device_name
            }
            
            encoded_jwt = jwt.encode(
                claims,
                self.secret_key,
                algorithm=self.algorithm
            )
            
            # 添加令牌管理器
            token = Token(
                token=encoded_jwt,
                username=data["username"],
                user_id=data["user_id"],
                expire=expire,
                token_type="access",
                device_id=device_id,
                device_name=device_name
            )
            self.add_access_token(claims, token=encoded_jwt, owner_id=data["user_id"])
            
            return {
                "success": True,
                "token": encoded_jwt
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create access token: {str(e)}"
            }

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
        return {
            "success": True,
            "hash": self.pwd_context.hash(password)
        }

    def list_user_devices(self, user_id: str) -> Dict[str, Any]:
        """列出用户的所有已登录设备"""
        try:
            refresh_data = self._refresh_tokens.get(user_id) or {}
            devices = refresh_data.keys()

            return {
                "success": True,
                "devices": devices
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list devices: {str(e)}"
            }

    def revoke_user_access_tokens(self, user_id: str) -> dict:
        """仅撤销指定用户的所有访问令牌
        
        Args:
            user_id: 用户ID
            
        Returns:
            dict: 操作结果
                - success: 是否成功
                - message: 成功消息，包含撤销的令牌数量
                - error: 错误信息（如果失败）
        """
        try:
            # 获取用户的所有访问令牌
            user_tokens = self._access_tokens.get(user_id, {})
            token_count = len(user_tokens)
            
            # 清除用户的所有访问令牌
            if user_id in self._access_tokens:
                del self._access_tokens[user_id]
            
            return {
                "success": True,
                "message": f"已撤销 {token_count} 个访问令牌"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"撤销访问令牌失败: {str(e)}"
            }

    def revoke_all_user_tokens(self, user_id: str) -> dict:
        """撤销用户的所有访问令牌和刷新令牌
        
        Args:
            user_id: 用户ID
            
        Returns:
            dict: 操作结果
        """
        try:
            # 1. 撤销访问令牌
            access_count = len(self._access_tokens.get(user_id, {}))
            if user_id in self._access_tokens:
                del self._access_tokens[user_id]
            
            # 2. 撤销刷新令牌
            refresh_data = self._refresh_tokens.get(user_id)
            refresh_count = len(refresh_data) if refresh_data else 0
            self._refresh_tokens.set(value={}, owner_id=user_id)
            
            return {
                "success": True,
                "message": f"已撤销 {access_count} 个访问令牌和 {refresh_count} 个刷新令牌"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"撤销所有令牌失败: {str(e)}"
            }

    def revoke_device_tokens(self, user_id: str, device_id: str) -> dict:
        """撤销指定设备的所有令牌
        
        Args:
            user_id: 用户ID
            device_id: 设备ID
            
        Returns:
            dict: 操作结果
        """
        try:
            # 1. 撤销访问令牌
            access_tokens = self._access_tokens.get(user_id, {})
            if device_id in access_tokens:
                del access_tokens[device_id]
                self._access_tokens[user_id] = access_tokens
            
            # 2. 撤销刷新令牌
            refresh_data = self._refresh_tokens.get(user_id) or {}
            had_refresh = device_id in refresh_data
            if had_refresh:
                del refresh_data[device_id]
                self._refresh_tokens.set(value=refresh_data, owner_id=user_id)
            
            return {
                "success": True,
                "message": f"已撤销设备 {device_id} 的所有令牌"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"撤销设备令牌失败: {str(e)}"
            }

    def is_access_token_revoked(self, token: str, user_id: str) -> bool:
        """检查访问令牌是否已被撤销
        
        Args:
            token: 访问令牌字符串
            user_id: 用户ID
            
        Returns:
            bool: 如果令牌被撤销返回True，否则返回False
        """
        try:
            # 遍历用户所有设备的令牌
            user_tokens = self._access_tokens.get(user_id, {})
            return not any(
                device_data.get("token") == token
                for device_data in user_tokens.values()
            )
        except Exception as e:
            return True

    def is_refresh_token_revoked(self, token: str, user_id: str) -> bool:
        """检查刷新令牌是否已被撤销
        
        Args:
            token: 刷新令牌字符串
            user_id: 用户ID
            
        Returns:
            bool: 如果令牌被撤销返回True，否则返回False
        """
        try:
            # 遍历用户所有设备的令牌
            refresh_data = self._refresh_tokens.get(user_id) or {}
            return not any(
                device_data.get("token") == token
                for device_data in refresh_data.values()
            )
        except Exception as e:
            return True

    def refresh_access_token(self, refresh_token: str, user_id: str) -> Dict[str, Any]:
        """使用刷新令牌颁发新的访问令牌
        
        Args:
            refresh_token: 刷新令牌
            user_id: 用户ID
            
        Returns:
            Dict[str, Any]: 结果字典
                - success: 是否成功
                - token: 新的访问令牌
                - error: 错误信息
        """
        try:
            # 验证刷新令牌是否有效
            if self.is_refresh_token_revoked(refresh_token, user_id):
                return {
                    "success": False,
                    "error": "Refresh token has been revoked"
                }
            
            # 解码刷新令牌获取信息
            refresh_claims = jwt.decode(
                refresh_token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # 创建新的访问令牌，继承原有的用户信息
            token_data = {
                "user_id": user_id,
                "username": refresh_claims.get("username"),
                "roles": refresh_claims.get("roles", []),
                "device_id": refresh_claims.get("device_id"),
                "device_name": refresh_claims.get("device_name")
            }
            
            return self.create_access_token(token_data)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to refresh access token: {str(e)}"
            }
