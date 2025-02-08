from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Response
from pathlib import Path
from calendar import timegm
from rocksdict import RDict, Options, ColumnFamilyDescriptor

from ...envir import get_env
from ...io.rocksdict import IndexedRocksDB
from ..result import Result

__JWT_SECRET_KEY__ = get_env("JWT_SECRET_KEY")
__JWT_ALGORITHM__ = get_env("JWT_ALGORITHM")
__ACCESS_TOKEN_EXPIRE_MINUTES__ = get_env("ACCESS_TOKEN_EXPIRE_MINUTES")
__REFRESH_TOKEN_EXPIRE_DAYS__ = get_env("REFRESH_TOKEN_EXPIRE_DAYS")

from enum import Enum

import logging

logger = logging.getLogger(__name__)

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
    def parse_token(cls, token: str) -> Self:
        """从JWT令牌中解析令牌信息"""
        return cls.model_validate(jwt.decode(
            token,
            get_env().JWT_SECRET_KEY,
            algorithms=[get_env().JWT_ALGORITHM]
        ))
    
    @classmethod
    def create_refresh_token(cls, user_id: str, username: str, roles: List[str], device_id: str = None) -> Self:
        """创建刷新令牌"""
        return cls(
            token_type=TokenType.REFRESH,
            user_id=user_id,
            username=username,
            roles=roles,
            device_id=device_id,
            iat=int(datetime.utcnow().timestamp()),
            exp=int((datetime.utcnow() + timedelta(days=__REFRESH_TOKEN_EXPIRE_DAYS__)).timestamp())
        )

    @classmethod
    def create_access_token(cls, user_id: str, username: str, roles: List[str], device_id: str = None) -> Self:
        """创建访问令牌"""
        return cls(
            token_type=TokenType.ACCESS,
            user_id=user_id,
            username=username,
            roles=roles,
            device_id=device_id,
            iat=int(datetime.utcnow().timestamp()),
            exp=int((datetime.utcnow() + timedelta(minutes=__ACCESS_TOKEN_EXPIRE_MINUTES__)).timestamp())
        )
    

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        from_attributes=True
    )

    # 根据设备的令牌信息    
    token_type: TokenType = Field(..., description="令牌类型")
    device_id: str = Field(default_factory=lambda: f"device_{uuid.uuid4().hex[:8]}", description="设备ID")
    iat: int = Field(default_factory=lambda: int(datetime.utcnow().timestamp()), description="令牌创建时间")
    exp: int = Field(default=0, description="令牌过期时间")

    # 用户信息
    user_id: str = Field(..., description="用户唯一标识")
    username: str = Field(..., description="用户名")
    roles: List[str] = Field(..., description="用户角色列表")

    @property
    def key(self) -> str:
        """每用户的每个设备可以有一个刷新令牌和访问令牌"""
        return f"token:{self.user_id}:{self.token_type}:{self.device_id}"
    
    def update_exp(self, duration: timedelta) -> Self:
        """更新令牌过期时间

        Example:
            token.update_exp(timedelta(days=1))
            token.update_exp(timedelta(minutes=10))
        """
        self.exp = int((datetime.utcnow() + duration).timestamp())
        return self
    
    def revoke(self) -> Self:
        """撤销令牌"""
        self.exp = 0
        return self

    def jwt_encode(self) -> str:
        """将令牌信息转换为JWT令牌"""
        return jwt.encode(
            self.model_dump(include={"user_id", "username", "roles", "device_id", "expired_at"}),
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

        # 刷新令牌保存在数据库中
        self._db = db

        # 访问令牌保存在内存中
        # 键为 user_id
        # 值也是字典，每个元素的键是 device_id，值是 TokenClaims 结构
        self._access_tokens: Dict[str, Dict[str, TokenClaims]] = {}

    def get_user_access_tokens(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """获取访问令牌"""
        return self._access_tokens.get(user_id, {})

    def get_user_refresh_tokens(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """获取刷新令牌

        此处为了实现更简洁，直接从 rocksdb 中获取；
        在并发访问时性能要求较高时可以直接升级为从内存数据库或基于缓存的消息队列服务中获取
        """
        tokens = self._db.items(prefix=TokenClaims.get_refresh_token_prefix(user_id))
        if tokens:
            return {token.device_id: TokenClaims.model_validate(token) for token in tokens}
        return {}
    
    def add_refresh_token(self, user_id: str, username: str, roles: List[str], device_id: str) -> TokenClaims:
        """保存刷新令牌到数据库"""
        claims = TokenClaims.create_refresh_token(user_id, username, roles, device_id)
        claims.update_exp(timedelta(days=__REFRESH_TOKEN_EXPIRE_DAYS__))
        self._db.put(TokenClaims.get_refresh_token_key(user_id, device_id), claims.model_dump())
        return claims
    
    def verify_access_token(self, token: str) -> Result[TokenClaims]:
        """验证 JWT 访问令牌，如果有必要就使用刷新令牌刷新"""
        try:
            unverified = jwt.decode(
                token,
                key=None,
                options={'verify_signature': False}
            )

            try:
                # 验证访问令牌
                valid_data = jwt.decode(
                    token,
                    key=__JWT_SECRET_KEY__,
                    algorithms=[__JWT_ALGORITHM__],
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'require_exp': True,
                    }
                )
                user_id = unverified.get("user_id", None)
                device_id = unverified.get("device_id", None)
                if not user_id or not device_id:
                    return Result.fail("无效的令牌：缺少user_id或device_id")

                logger.info(f"访问令牌验证成功: {unverified}")
                return Result.ok(data=TokenClaims.model_validate(valid_data))

            except jwt.JWTError:
                # 访问令牌验证失败，尝试使用刷新令牌刷新
                return self._refresh_access_token(
                    unverified.get("user_id", None),
                    unverified.get("username", None),
                    unverified.get("roles", None),
                    unverified.get("device_id", None)
                )

            except Exception as e:
                return Result.fail(f"令牌验证错误: {str(e)}")

        except Exception as e:
            return Result.fail(f"令牌验证错误: {str(e)}")
    
    def _refresh_access_token(self, user_id: str, username: str, roles: List[str], device_id: str) -> Result[str]:
        """使用 Refresh-Token 刷新令牌颁发新的 Access-Token"""

        try:
            all_refresh_tokens = self.get_user_refresh_tokens(user_id)
            refresh_token_data = all_refresh_tokens.get(device_id, None)
            if not refresh_token_data:
                return Result.fail("没有找到刷新令牌")

            refresh_token_claims = TokenClaims.model_validate(refresh_token_data)
            refresh_token = refresh_token_claims.jwt_encode()
            
            # 验证刷新令牌
            jwt.decode(
                refresh_token,
                key=__JWT_SECRET_KEY__,
                algorithms=[__JWT_ALGORITHM__],
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'require_exp': True,
                }
            )
            
            # 刷新访问令牌
            new_access_token = self._update_access_token(
                user_id,
                username,
                roles,
                device_id
            )
            logger.info(f"刷新访问令牌成功: {new_access_token}")
            return Result.ok(data=new_access_token)

        except jwt.JWTError:
            return Result.fail("令牌验证失败")

        except Exception as e:
            return Result.fail(f"令牌验证错误: {str(e)}")

    def _update_access_token(self, user_id: str, username: str, roles: List[str], device_id: str) -> TokenClaims:
        """更新内存中的访问令牌"""

        # 更新令牌过期时间
        claims = TokenClaims.create_access_token(user_id, username, roles, device_id)
        claims.update_exp(timedelta(minutes=__ACCESS_TOKEN_EXPIRE_MINUTES__))

        # 更新访问令牌
        if self._access_tokens.get(user_id, None):
            self._access_tokens[user_id][device_id] = claims
        else:
            self._access_tokens[user_id] = {device_id: claims}
        
        # 返回更新后的令牌
        return self._access_tokens[user_id][device_id]

    def revoke_refresh_token(self, user_id: str, device_id: str) -> None:
        """撤销数据库中的刷新令牌

        退出时，应当撤销指定设备的刷新令牌和访问令牌；
        在用户怀疑令牌被盗用时，应当撤销所有设备的刷新令牌和访问令牌，这可以强制用户重新登录来获得新的刷新令牌。
        """
        claims = TokenClaims.model_validate(self._db.get(TokenClaims.get_refresh_token_key(user_id, device_id)))
        claims.revoke()
        self._db.put(TokenClaims.get_refresh_token_key(user_id, device_id), claims.model_dump())
    
    def revoke_access_token(self, user_id: str, device_id: str = None) -> None:
        """撤销内存中的访问令牌"""
        if device_id:
            if self._access_tokens.get(user_id, None):
                del self._access_tokens[user_id][device_id]
        else:
            del self._access_tokens[user_id]
