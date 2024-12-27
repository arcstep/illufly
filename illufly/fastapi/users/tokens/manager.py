from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Response
from pathlib import Path
from calendar import timegm

from ....config import get_env
from ....io import ConfigStoreProtocol, JiaoziCache
from ...result import Result
from ..dependencies import AuthDependencies
from .models import TokenClaims

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
    - ILLUFLY_CONFIG_STORE_DIR: 令牌存储路径
    
    安全建议：
    1. 访问令牌过期时间建议设置为15-30分钟
    2. 刷新令牌过期时间建议设置为7-14天
    3. 敏感操作前应验证令牌的角色权限
    4. 确保使用HTTPS传输所有令牌
    5. 定期清理过期令牌
    6. 在可疑活动时主动撤销用户的所有令牌
    """
    
    def __init__(self, storage: Optional[ConfigStoreProtocol] = None):
        """初始化认证管理器"""
        if storage is None:
            storage = JiaoziCache(
                data_dir=Path(get_env("ILLUFLY_CONFIG_STORE_DIR")),
                filename="tokens.json",
                data_class=Dict[str, Dict[str, Dict[str, Any]]]
            )
        self._refresh_tokens = storage
        self._access_tokens: Dict[str, Dict[str, Any]] = {}
        
        self.dependencies = AuthDependencies(self)

        self.secret_key = get_env("FASTAPI_SECRET_KEY")
        if not self.secret_key:
            raise ValueError("FASTAPI_SECRET_KEY must be properly configured")
            
        self.algorithm = get_env("FASTAPI_ALGORITHM")
        if self.algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported JWT algorithm: {self.algorithm}")

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
            
            current_time = int(datetime.utcnow().timestamp())
            
            if owner_id not in self._access_tokens:
                self._access_tokens[owner_id] = {}
            
            user_tokens = self._access_tokens[owner_id]
            
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in user_tokens.items()
                if isinstance(token_data, dict) and
                   isinstance(token_data.get("claims"), TokenClaims) and
                   token_data["claims"].exp > current_time
            }
            
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
            
            current_time = int(datetime.utcnow().timestamp())
            refresh_data = self._refresh_tokens.get(owner_id) or {}
            
            valid_tokens = {
                d_id: token_data
                for d_id, token_data in refresh_data.items()
                if token_data["claims"].exp > current_time
            }
            
            valid_tokens[device_id] = {"claims": claims, "token": token}
            self._refresh_tokens.set(value=valid_tokens, owner_id=owner_id)
            
        except Exception as e:
            raise

    def verify_jwt(self, token: str, verify_exp: bool = True, token_type: str = "access") -> Result[TokenClaims]:
        """验证JWT令牌"""
        try:
            unverified = jwt.decode(
                token,
                key=None,
                options={"verify_signature": False}
            )
            
            try:
                payload = jwt.decode(
                    token,
                    key=self.secret_key,
                    algorithms=[self.algorithm],
                    options={
                        'verify_signature': True,
                        'verify_exp': verify_exp,
                        'verify_iat': True,
                        'require_exp': True,
                        'require_iat': True,
                        'leeway': 0,
                    }
                )
                
                claims = TokenClaims.model_validate(payload)
                
                if token_type == "access" and self.is_access_token_revoked(token, claims.user_id):
                    return Result.fail("令牌已被撤销")
                elif token_type == "refresh" and self.is_refresh_token_revoked(token, claims.user_id):
                    return Result.fail("令牌已被撤销")
                
                return Result.ok(data=claims)
                
            except jwt.ExpiredSignatureError:
                if token_type == "access":
                    user_id = unverified.get("user_id")
                    device_id = unverified.get("device_id")
                    
                    if not user_id or not device_id:
                        return Result.fail("无效的令牌：缺少user_id或device_id")
                    
                    refresh_data = self._refresh_tokens.get(user_id) or {}
                    device_tokens = refresh_data.get(device_id, {})
                    refresh_token = device_tokens.get("token")
                    
                    if refresh_token:
                        refresh_result = self.refresh_access_token(refresh_token, user_id)
                        if refresh_result.success:
                            return Result.ok(
                                data=TokenClaims(
                                    token=token,
                                    payload=unverified,
                                    new_token=refresh_result.data
                                )
                            )
                return Result.fail("令牌已过期")
                
            except jwt.JWTError as e:
                return Result.fail(f"无效的令牌: {str(e)}")
                
        except Exception as e:
            return Result.fail(f"令牌验证错误: {str(e)}")

    def create_refresh_token(self, data: Dict[str, Any]) -> Result[str]:
        """创建刷新令牌"""
        try:
            current_time = datetime.utcnow()
            expire = current_time + timedelta(days=self.refresh_token_expire_days)            
            claims = TokenClaims(
                **data,
                exp=timegm(expire.utctimetuple()),
                iat=timegm(current_time.utctimetuple()),
                token_type="refresh",
            )
            
            encoded_jwt = jwt.encode(
                claims.model_dump(),
                self.secret_key,
                algorithm=self.algorithm
            )
            
            self.add_refresh_token(claims, token=encoded_jwt, owner_id=data["user_id"])
            return Result.ok(data=encoded_jwt)
        except Exception as e:
            return Result.fail(f"创建刷新令牌失败: {str(e)}")

    def create_access_token(self, data: dict) -> Result[str]:
        """创建访问令牌"""
        try:
            current_time = datetime.utcnow()
            expire = current_time + timedelta(minutes=self.access_token_expire_minutes)
            claims = TokenClaims(
                **data,
                exp=timegm(expire.utctimetuple()),
                iat=timegm(current_time.utctimetuple()),
                token_type="access",
            )
            
            encoded_jwt = jwt.encode(
                claims.model_dump(),
                self.secret_key,
                algorithm=self.algorithm
            )
            
            self.add_access_token(claims, token=encoded_jwt, owner_id=data["user_id"])
            return Result.ok(data=encoded_jwt)
        except Exception as e:
            return Result.fail(f"创建访问令牌失败: {str(e)}")

    def set_auth_cookies(
        self, response: Response,
        access_token: str = None,
        refresh_token: str = None,
        device_id: str = None
    ) -> None:
        """设置认证Cookie"""
        try:
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

            if device_id:
                response.set_cookie(
                    key="device_id",
                    value=device_id,
                    httponly=True,
                    secure=True,
                    samesite="Lax"
                )
            
        except Exception as e:
            print(">>> 设置 cookies 时发生错误:", str(e))
            raise

    def list_user_devices(self, user_id: str) -> Result[List[str]]:
        """列出用户的所有已登录设备"""
        try:
            refresh_data = self._refresh_tokens.get(user_id) or {}
            return Result.ok(data=list(refresh_data.keys()))
        except Exception as e:
            return Result.fail(f"获取设备列表失败: {str(e)}")

    def revoke_user_access_tokens(self, user_id: str) -> Result[None]:
        """仅撤销指定用户的所有访问令牌"""
        try:
            user_tokens = self._access_tokens.get(user_id, {})
            token_count = len(user_tokens)
            
            if user_id in self._access_tokens:
                del self._access_tokens[user_id]
            
            return Result.ok(message=f"已撤销 {token_count} 个访问令牌")
        except Exception as e:
            return Result.fail(f"撤销访问令牌失败: {str(e)}")

    def revoke_all_user_tokens(self, user_id: str) -> Result[None]:
        """撤销用户的所有访问令牌和刷新令牌"""
        try:
            access_count = len(self._access_tokens.get(user_id, {}))
            if user_id in self._access_tokens:
                del self._access_tokens[user_id]
            
            refresh_data = self._refresh_tokens.get(user_id)
            refresh_count = len(refresh_data) if refresh_data else 0
            self._refresh_tokens.set(value={}, owner_id=user_id)
            
            return Result.ok(
                message=f"已撤销 {access_count} 个访问令牌和 {refresh_count} 个刷新令牌"
            )
        except Exception as e:
            return Result.fail(f"撤销所有令牌失败: {str(e)}")

    def revoke_device_tokens(self, user_id: str, device_id: str) -> Result[None]:
        """撤销指定设备的所有令牌"""
        try:
            access_tokens = self._access_tokens.get(user_id, {})
            if device_id in access_tokens:
                del access_tokens[device_id]
                self._access_tokens[user_id] = access_tokens
            
            refresh_data = self._refresh_tokens.get(user_id) or {}
            had_refresh = device_id in refresh_data
            if had_refresh:
                del refresh_data[device_id]
                self._refresh_tokens.set(value=refresh_data, owner_id=user_id)
            
            return Result.ok(message=f"已撤销设备 {device_id} 的所有令牌")
        except Exception as e:
            return Result.fail(f"撤销设备令牌失败: {str(e)}")

    def is_access_token_revoked(self, token: str, user_id: str) -> bool:
        """检查访问令牌是否已被撤销"""
        try:
            user_tokens = self._access_tokens.get(user_id, {})
            return not any(
                device_data.get("token") == token
                for device_data in user_tokens.values()
            )
        except Exception as e:
            return True

    def is_refresh_token_revoked(self, token: str, user_id: str) -> bool:
        """检查刷新令牌是否已被撤销"""
        try:
            refresh_data = self._refresh_tokens.get(user_id) or {}
            return not any(
                device_data.get("token") == token
                for device_data in refresh_data.values()
            )
        except Exception as e:
            return True

    def refresh_access_token(self, refresh_token: str, user_id: str) -> Result[str]:
        """使用 Refresh-Token 刷新令牌颁发新的 Access-Token"""
        try:
            verify_result = self.verify_jwt(refresh_token, verify_exp=True, token_type="refresh")
            if not verify_result.success:
                return Result.fail(verify_result.error)
            
            refresh_claims = verify_result.data
            
            required_fields = ["user_id", "device_id"]
            for field in required_fields:
                if field not in refresh_claims.model_dump():
                    return Result.fail(f"令牌缺少必要字段: {field}")
            
            if refresh_claims.user_id != user_id:
                return Result.fail("用户ID不匹配")
            
            token_data = {
                "user_id": user_id,
                "username": refresh_claims.username,
                "roles": refresh_claims.roles,
                "device_id": refresh_claims.device_id,
            }
            
            return self.create_access_token(token_data)
            
        except Exception as e:
            return Result.fail(f"刷新访问令牌失败: {str(e)}")
