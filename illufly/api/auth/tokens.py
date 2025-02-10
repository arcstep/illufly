from typing import Dict, Any, Optional, Union, List, Tuple, Self
from datetime import datetime, timedelta, timezone
from fastapi import Response
from pathlib import Path
from calendar import timegm
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

import jwt
import logging

from ...envir import get_env
from ...rocksdb import IndexedRocksDB, CachedRocksDB
from ..models import Result

__JWT_SECRET_KEY__ = get_env("FASTAPI_SECRET_KEY")
__JWT_ALGORITHM__ = get_env("FASTAPI_ALGORITHM")
__ACCESS_TOKEN_EXPIRE_MINUTES__ = int(get_env("FASTAPI_ACCESS_TOKEN_EXPIRE_MINUTES"))
__REFRESH_TOKEN_EXPIRE_DAYS__ = int(get_env("FASTAPI_REFRESH_TOKEN_EXPIRE_DAYS"))

class TokenType(str, Enum):
    """令牌类型"""
    ACCESS = "access"
    REFRESH = "refresh"

class TokenClaims(BaseModel):
    """令牌信息"""

    @classmethod
    def get_refresh_token_prefix(cls, user_id: str) -> str:
        """获取刷新令牌前缀"""
        return f"token:{user_id}:refresh:"

    @classmethod
    def get_refresh_token_key(cls, user_id: str, device_id: str) -> str:
        """获取刷新令牌键"""
        return f"{cls.get_refresh_token_prefix(user_id)}:{device_id}"

    @classmethod
    def get_access_token_prefix(cls, user_id: str) -> str:
        """获取访问令牌前缀"""
        return f"token:{user_id}:access:"

    @classmethod
    def get_access_token_key(cls, user_id: str, device_id: str) -> str:
        """获取访问令牌键"""
        return f"{cls.get_access_token_prefix(user_id)}:{device_id}"
    
    @classmethod
    def create_refresh_token(cls, user_id: str, username: str, roles: List[str], device_id: str = None, **kwargs) -> Self:
        """创建刷新令牌"""
        return cls(
            token_type=TokenType.REFRESH,
            user_id=user_id,
            username=username,
            roles=roles,
            device_id=device_id,
            exp=datetime.utcnow() + timedelta(days=__REFRESH_TOKEN_EXPIRE_DAYS__)
        )

    @classmethod
    def create_access_token(cls, user_id: str, username: str, roles: List[str], device_id: str = None, **kwargs) -> Self:
        """创建访问令牌"""
        return cls(
            token_type=TokenType.ACCESS,
            user_id=user_id,
            username=username,
            roles=roles,
            device_id=device_id,
            exp=datetime.utcnow() + timedelta(minutes=__ACCESS_TOKEN_EXPIRE_MINUTES__)
        )

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True
    )

    # 根据设备的令牌信息    
    token_type: TokenType = Field(..., description="令牌类型")
    device_id: str = Field(default_factory=lambda: f"device_{uuid.uuid4().hex[:8]}", description="设备ID")
    iat: datetime = Field(default_factory=datetime.utcnow, description="令牌创建时间")
    exp: datetime = Field(default=0, description="令牌过期时间")

    # 用户信息
    user_id: str = Field(..., description="用户唯一标识")
    username: str = Field(..., description="用户名")
    roles: List[str] = Field(..., description="用户角色列表")

    def revoke(self) -> Self:
        """撤销令牌"""
        self.exp = 0
        return self

    def jwt_encode(self) -> str:
        """将令牌信息转换为JWT令牌"""
        return jwt.encode(
            payload=self.model_dump(),
            key=__JWT_SECRET_KEY__,
            algorithm=__JWT_ALGORITHM__
        )

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
    """
    
    def __init__(self, db: IndexedRocksDB):
        """初始化认证管理器

        刷新令牌持久化保存在 rocksdb 中，访问令牌保存在内存中。
        刷新令牌应当在用户登录时颁发，访问令牌应当在用户每次授权请求时验证，如果缺少合法的访问令牌就使用刷新令牌重新颁发；
        """

        self._logger = logging.getLogger(__name__)

        # 刷新令牌持久化保存在数据库中
        self._cache = CachedRocksDB(db)

        # 访问令牌在客户端和服务器端之间交换
        # 生成过的访问令牌都保存在这个白名单中，但也可以通过撤销操作删除
        # 白名单格式：
        #   - 键为 user_id
        #   - 值也是字典，每个元素的键是 device_id，值是 TokenClaims 结构
        self._access_tokens: Dict[str, Dict[str, TokenClaims]] = {}

    def existing_access_token(self, user_id: str, device_id: str) -> bool:
        """检查访问令牌是否存在"""
        return self._access_tokens.get(user_id, {}).get(device_id, None) is not None
    
    def get_refresh_token(self, user_id: str, device_id: str) -> TokenClaims:
        """获取刷新令牌"""
        token_key = TokenClaims.get_refresh_token_key(user_id, device_id)
        token_claims = self._cache.get(token_key)
        if token_claims:
            return token_claims.jwt_encode()
        return None
    
    def update_refresh_token(self, user_id: str, username: str, roles: List[str], device_id: str) -> TokenClaims:
        """保存刷新令牌到数据库"""
        # 创建刷新令牌
        claims = TokenClaims.create_refresh_token(user_id, username, roles, device_id)

        # 保存刷新令牌到数据库
        token_key = TokenClaims.get_refresh_token_key(user_id, device_id)
        self._cache.put(token_key, claims)

        self._logger.info(f"已更新刷新令牌: {claims}")
        return claims
    
    def verify_access_token(self, token: str) -> Result[TokenClaims]:
        """验证 JWT 访问令牌，如果有必要就使用刷新令牌刷新"""
        try:
            unverified = jwt.decode(
                token,
                key=None,
                options={'verify_signature': False, 'verify_exp': False}
            )
            self._logger.info(f"未验证的令牌: {unverified}")
            user_id = unverified.get("user_id", None)
            device_id = unverified.get("device_id", None)
            if not user_id or not device_id:
                return Result.fail("无效的令牌：缺少user_id或device_id")

            try:
                # 验证访问令牌
                valid_data = jwt.decode(
                    token,
                    key=__JWT_SECRET_KEY__,
                    algorithms=[__JWT_ALGORITHM__],
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'require': ['exp', 'iat'],
                    }
                )

                # 白名单验证，确定是否撤销
                if self.existing_access_token(user_id, device_id):
                    self._logger.info(f"访问令牌验证成功: {valid_data}")
                    valid_data["token_type"] = TokenType.ACCESS
                    return Result.ok(data=valid_data)
                else:
                    return Result.fail("访问令牌已撤销")

            except jwt.ExpiredSignatureError:
                # 访问令牌验证失败，尝试使用刷新令牌刷新
                self._logger.info(f"访问令牌验证失败，尝试使用刷新令牌刷新")
                return self.refresh_access_token(
                    user_id=unverified.get("user_id", None),
                    username=unverified.get("username", None),
                    roles=unverified.get("roles", None),
                    device_id=unverified.get("device_id", None)
                )

            except Exception as e:
                return Result.fail(f"令牌验证错误: {str(e)}")

        except Exception as e:
            return Result.fail(f"令牌验证错误: {str(e)}")
    
    def refresh_access_token(self, user_id: str, username: str, roles: List["UserRole"], device_id: str) -> Result[str]:
        """使用 Refresh-Token 刷新令牌颁发新的 Access-Token"""

        try:
            refresh_token = self.get_refresh_token(user_id, device_id)
            if not refresh_token:
                return Result.fail("没有找到刷新令牌")

            self._logger.info(f"找到刷新令牌: {refresh_token}")
            
            # 验证刷新令牌
            jwt.decode(
                jwt=refresh_token,
                key=__JWT_SECRET_KEY__,
                algorithms=[__JWT_ALGORITHM__],
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'require': ['exp', 'iat'],
                }
            )
            
            # 刷新访问令牌
            new_access_token = self._update_access_token(
                user_id,
                username,
                roles,
                device_id
            )
            self._logger.info(f"已重新颁发访问令牌: {new_access_token}")
            return Result.ok(data=new_access_token.model_dump(), message="访问令牌刷新成功")

        except jwt.ExpiredSignatureError as e:
            return Result.fail(f"令牌验证失败: {str(e)}")

        except Exception as e:
            return Result.fail(f"令牌验证错误: {str(e)}")

    def _update_access_token(self, user_id: str, username: str, roles: List[str], device_id: str) -> TokenClaims:
        """更新内存中的访问令牌"""

        # 生成新的访问令牌
        claims = TokenClaims.create_access_token(user_id, username, roles, device_id)

        # 更新访问令牌
        if self._access_tokens.get(user_id, None):
            self._access_tokens[user_id][device_id] = claims
        else:
            self._access_tokens[user_id] = {device_id: claims}
        
        # 返回更新后的令牌
        return claims

    def revoke_refresh_token(self, user_id: str, device_id: str) -> None:
        """撤销数据库中的刷新令牌"""
        token_key = TokenClaims.get_refresh_token_key(user_id, device_id)
        claims = self._cache.get(token_key)
        if claims:
            claims.revoke()
            self._cache.put(token_key, claims)
            self._logger.info(f"刷新令牌已撤销: {token_key}")
    
    def revoke_access_token(self, user_id: str, device_id: str = None) -> None:
        """撤销内存中的访问令牌"""
        if device_id:
            if self._access_tokens.get(user_id, None):
                del self._access_tokens[user_id][device_id]
        else:
            del self._access_tokens[user_id]
