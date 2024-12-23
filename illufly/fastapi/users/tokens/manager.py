from typing import Dict, Any, Optional, Set, Union, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from jose import jwt, JWTError
from fastapi import Response
from pathlib import Path
from calendar import timegm

import re
import uuid
import os

from ....io import ConfigStoreProtocol, FileConfigStore
from ..dependencies import AuthDependencies
from .models import TokenClaims

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

@dataclass
class TokensManager:
    """令牌管理器，用于处理JWT令牌的创建、验证和管理。
    
    该类提供了完整的JWT令牌管理解决方案，包括：
    - JWT令牌的创建和验证
    - 访问令牌和刷新令牌的生命周期管理
    - 多设备登录支持
    - 令牌撤销管理
    
    主要特性：
    - 支持登陆验证和角色验证
    - 基于JWT的双令牌认证系统
    - 支持访问令牌失效时根据有效的刷新令牌自动刷新
    - 支持在刷新令牌未过期时实现零登录
    - 支持多设备同时登录
    - 支持撤销在用设备的令牌
    - 支持强制撤销所有设备的令牌
    - 支持自动清理过期令牌
    
    使用示例:
    ```python
    # 1. 初始化令牌管理器
    tokens_manager = TokensManager()
    
    # 2. 创建刷新令牌（登录）
    user_data = {
        "user_id": "user123",
        "username": "johndoe",
        "roles": ["user"],
        "device_id": "browser_chrome_123",
    }
    
    refresh_result = tokens_manager.create_refresh_token(user_data)
    if refresh_result["success"]:
        refresh_token = refresh_result["token"]

    # 3. 使用刷新令牌获取访问令牌（支持零登录）
    access_result = tokens_manager.refresh_access_token(
        refresh_token, 
        user_data["user_id"]
    )
    if access_result["success"]:
        access_token = access_result["token"]
    
    # 4. 验证令牌（日常验证）
    verify_result = tokens_manager.verify_jwt(
        access_token, 
        verify_exp=True,
        token_type="access"
    )
    
    # 5. 查看用户的所有登录设备
    devices = tokens_manager.list_user_devices(user_data["user_id"])
    
    # 6. 撤销当前登录设备上的令牌（退出）
    tokens_manager.revoke_device_tokens(
        user_data["user_id"], 
        user_data["device_id"]
    )
    
    # 7. 强制撤销所有设备上的令牌（强制要求重新登录，防止盗用）
    tokens_manager.revoke_all_user_tokens(user_data["user_id"])
    ```
    
    配置要求：
    可以通过以下环境变量修改系统配置的默认值：
    - FASTAPI_SECRET_KEY: JWT签名密钥
    - FASTAPI_ALGORITHM: JWT算法 (HS256, HS384, HS512)
    - ACCESS_TOKEN_EXPIRE_MINUTES: 访问令牌过期时间（分钟）
    - REFRESH_TOKEN_EXPIRE_DAYS: 刷新令牌过期时间（天）
    - ILLUFLY_FASTAPI_USERS_PATH: 令牌存储路径
    
    安全建议：
    1. 访问令牌过期时间建议设置为15-30分钟
    2. 刷新令牌过期时间建议设置为7-14天
    3. 敏感操作前应验证令牌的角色权限
    4. 确保使用HTTPS传输所有令牌
    5. 定期清理过期令牌
    6. 在可疑活动时主动撤销用户的所有令牌
    """
    
    def __init__(self, storage: Optional[ConfigStoreProtocol] = None, config_store_path: str = None):
        """初始化认证管理器
        
        Args:
            storage: 可选的令牌存储实现，默认使用文件存储
            
        Raises:
            ValueError: 如果必要的环境变量未正确配置
        """
        # 初始化存储
        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(config_store_path or __USERS_PATH__),
                filename="tokens.json",
                data_class=Dict[str, Dict[str, Dict[str, Any]]]
            )
        self._refresh_tokens = storage
        self._access_tokens: Dict[str, Token] = {}
        
        # 创建依赖管理器
        self.dependencies = AuthDependencies(self)

        # 令牌加密所需的必要的环境变量
        self.secret_key = get_env("FASTAPI_SECRET_KEY")
        if not self.secret_key:
            raise ValueError("FASTAPI_SECRET_KEY must be properly configured")
            
        self.algorithm = get_env("FASTAPI_ALGORITHM")
        if self.algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported JWT algorithm: {self.algorithm}")

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

    def add_access_token(self, claims: TokenClaims, token: str, owner_id: str) -> None:
        """添加访问令牌，同时清理过期的令牌"""
        try:
            device_id = claims.device_id
            if not device_id:
                raise ValueError("Device ID is required")
            
            # 获取用户当前的所有令牌
            current_time = int(datetime.utcnow().timestamp())
            
            # 确保用户字典存在
            if owner_id not in self._access_tokens:
                self._access_tokens[owner_id] = {}
            
            user_tokens = self._access_tokens[owner_id]
            
            # 过滤出未过期的令牌
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in user_tokens.items()
                if isinstance(token_data, dict) and  # 确保token_data是字典
                   isinstance(token_data.get("claims"), TokenClaims) and  # 确保claims是TokenClaims对象
                   token_data["claims"].exp > current_time
            }
            
            # 添加新令牌
            valid_tokens[device_id] = {"claims": claims, "token": token}
            self._access_tokens[owner_id] = valid_tokens
            
        except Exception as e:
            raise ValueError(f"Failed to add access token: {str(e)}")

    def add_refresh_token(self, claims: TokenClaims, token: str, owner_id: str) -> None:
        """添加刷新令牌，同时清理过期的令牌"""
        try:
            device_id = claims.device_id
            if not device_id:
                raise ValueError("Device ID is required")
            
            # 获取用户当前的所有令牌
            current_time = int(datetime.utcnow().timestamp())
            refresh_data = self._refresh_tokens.get(owner_id) or {}
            
            # 过滤出未过期的令牌
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in refresh_data.items()
                if token_data["claims"].exp > current_time
            }
            
            # 添加新令牌
            valid_tokens[device_id] = {"claims": claims, "token": token}
            self._refresh_tokens.set(value=valid_tokens, owner_id=owner_id)
            
        except Exception as e:
            raise

    def verify_jwt(self, token: str, verify_exp: bool = True, token_type: str = "access") -> Dict[str, Any]:
        """验证JWT令牌，如果是访问令牌且验证失败，尝试使用刷新令牌刷新
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
            
            try:
                payload = jwt.decode(
                    token,
                    key=self.secret_key,
                    algorithms=[self.algorithm],
                    options=options
                )
                
                # 检查令牌是否被撤销
                user_id = payload.get("user_id")
                device_id = payload.get("device_id")
                
                if not user_id or not device_id:
                    return {
                        "success": False,
                        "error": "Invalid token: missing user_id or device_id"
                    }
                
                if token_type == "access":
                    if self.is_access_token_revoked(token, user_id):
                        return {
                            "success": False,
                            "error": "Token has been revoked"
                        }
                elif token_type == "refresh":
                    if self.is_refresh_token_revoked(token, user_id):
                        return {
                            "success": False,
                            "error": "Token has been revoked"
                        }
                
                return {
                    "success": True,
                    "payload": payload
                }
                
            except jwt.ExpiredSignatureError:
                # 如果是访问令牌过期，尝试使用刷新令牌
                if token_type == "access":
                    user_id = unverified.get("user_id")
                    device_id = unverified.get("device_id")
                    
                    if not user_id or not device_id:
                        return {
                            "success": False,
                            "error": "Invalid token: missing user_id or device_id"
                        }
                    
                    # 查找相同设备的刷新令牌
                    refresh_data = self._refresh_tokens.get(user_id) or {}
                    device_tokens = refresh_data.get(device_id, {})
                    print(">>> device_tokens: ", device_tokens)
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
                    "error": "Token has expired"
                }
                
            except jwt.JWTError as e:
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
            current_time = datetime.utcnow()
            expire = current_time + timedelta(days=self.refresh_token_expire_days)            
            iat_timestamp = timegm(current_time.utctimetuple())
            exp_timestamp = timegm(expire.utctimetuple())
            
            claims = TokenClaims.from_dict({
                **data,
                "exp": exp_timestamp,
                "iat": iat_timestamp,
                "token_type": "refresh",
            })
            
            encoded_jwt = jwt.encode(
                claims.to_dict(),
                self.secret_key,
                algorithm=self.algorithm
            )
            
            self.add_refresh_token(claims, token=encoded_jwt, owner_id=data["user_id"])
            
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
        print(">>> data: ", data)
        try:
            current_time = datetime.utcnow()
            expire = current_time + timedelta(minutes=self.access_token_expire_minutes)            
            iat_timestamp = timegm(current_time.utctimetuple())
            exp_timestamp = timegm(expire.utctimetuple())
            
            claims = TokenClaims.from_dict({
                **data,
                "exp": exp_timestamp,
                "iat": iat_timestamp,
                "token_type": "access",
            })

            print(">>> claims: ", claims.to_dict())
            encoded_jwt = jwt.encode(
                claims.to_dict(),
                self.secret_key,
                algorithm=self.algorithm
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

    def set_auth_cookies(
        self, response: Response,
        access_token: str = None,
        refresh_token: str = None,
        device_id: str = None
    ) -> None:
        """设置认证Cookie"""
        print(">>> 开始设置 cookies...")
        print(">>> response 类型:", type(response))
        print(">>> access_token:", access_token[:20] if access_token else None)
        print(">>> refresh_token:", refresh_token[:20] if refresh_token else None)
        print(">>> device_id:", device_id)
        
        try:
            if access_token:
                print(">>> 设置 access_token cookie...")
                response.set_cookie(
                    key="access_token",
                    value=access_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax"
                )
                print(">>> access_token cookie 已设置")

            if refresh_token:
                print(">>> 设置 refresh_token cookie...")
                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=True,
                    samesite="Lax"
                )
                print(">>> refresh_token cookie 已设置")

            if device_id:
                print(">>> 设置 device_id cookie...")
                response.set_cookie(
                    key="device_id",
                    value=device_id,
                    httponly=True,
                    secure=True,
                    samesite="Lax"
                )
                print(">>> device_id cookie 已设置")
            
            print(">>> cookies 设置完成")
            
        except Exception as e:
            print(">>> 设置 cookies 时发生错误:", str(e))
            raise

    def list_user_devices(self, user_id: str) -> Dict[str, Any]:
        """列出用户的所有已登录设备"""
        try:
            refresh_data = self._refresh_tokens.get(user_id) or {}
            devices = list(refresh_data.keys())

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
        """检查访问令牌是否已��撤销
        
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
        """使用 Refresh-Token 刷新令牌颁发新的 Access-Token"""
        try:
            # 验证 Refresh-Token
            verify_result = self.verify_jwt(refresh_token, verify_exp=True, token_type="refresh")
            if not verify_result["success"]:
                return {
                    "success": False,
                    "error": verify_result["error"]
                }
            
            refresh_claims = verify_result["payload"]
            
            # 验证必要字段
            required_fields = ["user_id", "device_id"]
            for field in required_fields:
                if field not in refresh_claims:
                    return {
                        "success": False,
                        "error": f"Missing required field: {field}"
                    }
            
            # 验证用户ID匹配
            if refresh_claims["user_id"] != user_id:
                return {
                    "success": False,
                    "error": "User ID mismatch"
                }
            
            # 创建新的访问令牌
            token_data = {
                "user_id": user_id,
                "username": refresh_claims.get("username"),
                "roles": refresh_claims.get("roles", []),
                "device_id": refresh_claims.get("device_id", ""),
            }
            
            return self.create_access_token(token_data)
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to refresh access token: {str(e)}"
            }
