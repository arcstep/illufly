from typing import Dict, Any, Optional, Set, Union, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Response
import re
from pathlib import Path
import uuid

from ...config import get_env
from ..common import ConfigStoreProtocol, FileConfigStore
from .dependencies import AuthDependencies

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

@dataclass
class Token:
    """令牌数据模型"""
    token: str
    username: str
    user_id: str
    expire: datetime
    token_type: str
    device_id: str = "default"  # 默认设备ID
    device_name: str = "Default Device"  # 默认设备名称
    
    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "username": self.username,
            "user_id": self.user_id,
            "expire": self.expire.isoformat(),
            "token_type": self.token_type,
            "device_id": self.device_id,
            "device_name": self.device_name
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Token':
        return Token(
            token=data["token"],
            username=data["username"],
            user_id=data["user_id"],
            expire=datetime.fromisoformat(data["expire"]),
            token_type=data["token_type"],
            device_id=data.get("device_id", "unknown"),  # 兼容旧数据
            device_name=data.get("device_name", "Unknown Device")  # 兼容旧数据
        )
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expire

@dataclass
class TokenStorage:
    """令牌存储容器"""
    tokens: List[Token] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "tokens": [token.to_dict() for token in self.tokens]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TokenStorage':
        """从字典创建实例"""
        if not data or not isinstance(data, dict):
            return cls()
            
        tokens = []
        token_list = data.get("tokens", [])
        if isinstance(token_list, list):
            for token_data in token_list:
                try:
                    if isinstance(token_data, dict):
                        token = Token(
                            token=token_data["token"],
                            username=token_data["username"],
                            user_id=token_data["user_id"],
                            expire=datetime.fromisoformat(token_data["expire"]),
                            token_type=token_data["token_type"],
                            device_id=token_data.get("device_id", "default"),
                            device_name=token_data.get("device_name", "Default Device")
                        )
                        tokens.append(token)
                except Exception as e:
                    print(f"Error deserializing token: {e}")
                    continue
                    
        return cls(tokens=tokens)
    
    def __str__(self):
        return f"TokenStorage(tokens_count={len(self.tokens)})"

class AuthManager:
    def __init__(self, storage: Optional[ConfigStoreProtocol[TokenStorage]] = None):
        """初始化令牌管理器"""
        # 验证必要的环境变量
        self.secret_key = get_env("FASTAPI_SECRET_KEY")
        if not self.secret_key or self.secret_key == "MY-SECRET-KEY":
            raise ValueError("FASTAPI_SECRET_KEY must be properly configured")
            
        self.algorithm = get_env("FASTAPI_ALGORITHM")
        if self.algorithm not in ["HS256", "HS384", "HS512"]:
            raise ValueError(f"Unsupported JWT algorithm: {self.algorithm}")
            
        self.hash_method = get_env("HASH_METHOD")
        if self.hash_method not in ["argon2", "bcrypt", "pbkdf2_sha256"]:
            raise ValueError(f"Unsupported hash method: {self.hash_method}")
        
        # 初始化存储
        if storage is None:
            storage = FileConfigStore[TokenStorage](
                data_dir=Path(__USERS_PATH__),
                filename="tokens.json",
                serializer=lambda x: x.to_dict() if x else {"tokens": []},
                deserializer=TokenStorage.from_dict
            )
        self._storage = storage
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

    def add_token(self, token: str, username: str, user_id: str, expire_time: timedelta, 
                  token_type: str, device_id: str = None, device_name: str = None) -> None:
        """添加令牌"""
        try:
            expire = datetime.utcnow() + expire_time
            token_obj = Token(
                token=token,
                username=username,
                user_id=user_id,
                expire=expire,
                token_type=token_type,
                device_id=device_id or "default",
                device_name=device_name or "Default Device"
            )
            
            if token_type == "access":
                self._access_tokens[token] = token_obj
            else:  # refresh token
                storage = self._storage.get(owner_id=user_id)
                if not storage:
                    storage = TokenStorage()
                elif not isinstance(storage, TokenStorage):
                    storage = TokenStorage(tokens=[storage] if storage else [])
                
                # 如果是同一设备，移除旧令牌
                if device_id:
                    storage.tokens = [t for t in storage.tokens 
                                    if t.device_id != device_id and not t.is_expired()]
                
                storage.tokens.append(token_obj)
                self._storage.set(value=storage, owner_id=user_id)
                
        except Exception as e:
            print(f"Error adding token: {e}")
            raise

    def is_token_valid(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """检查令牌是否有效
        
        Args:
            token: 要检查的令牌
            token_type: 令牌类型 ("access" 或 "refresh")
            
        Returns:
            Dict[str, Any]: 包含验证结果的字典
        """
        print(f"\n=== 检查令牌有效性 ===")
        print(f">>> 令牌类型: {token_type}")
        
        try:
            # 1. 验证JWT格式和签名
            verify_result = self.verify_jwt(token)
            if not verify_result["success"]:
                print(f">>> JWT验证失败: {verify_result['error']}")
                return verify_result
            
            # 2. 检查令牌是否被撤销
            if token_type == "access":
                is_valid = token in self._access_tokens
                print(f">>> 访问令牌是否在内存中: {is_valid}")
                return {
                    "success": is_valid,
                    "error": None if is_valid else "Token has been invalidated"
                }
            else:
                # 对于刷新令牌，检查存储
                payload = verify_result["payload"]
                user_id = payload.get("user_id")
                if not user_id:
                    return {
                        "success": False,
                        "error": "Invalid token: missing user_id"
                    }
                
                storage = self._storage.get(owner_id=user_id)
                if not storage or not isinstance(storage, TokenStorage):
                    return {
                        "success": False,
                        "error": "No valid tokens found"
                    }
                
                is_valid = any(t.token == token and not t.is_expired() 
                              for t in storage.tokens)
                print(f">>> 刷新令牌是否有效: {is_valid}")
                return {
                    "success": is_valid,
                    "error": None if is_valid else "Token has been invalidated"
                }
                
        except Exception as e:
            error_msg = f"Failed to check token validity: {str(e)}"
            print(f">>> 错误: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

    def _remove_access_token(self, token: str) -> bool:
        """从内存缓存中移除访问令牌
        
        Returns:
            bool: 是否成功移除
        """
        if token in self._access_tokens:
            self._access_tokens.pop(token)
            return True
        return False

    def _clear_expired_access_tokens(self) -> None:
        """清理过期的访问令牌"""
        expired_tokens = [
            token for token, token_obj in self._access_tokens.items()
            if token_obj.is_expired()
        ]
        for token in expired_tokens:
            self._remove_access_token(token)

    def verify_jwt(self, token: str, verify_exp: bool = True) -> Dict[str, Any]:
        """验证JWT令牌
        
        Args:
            token: JWT令牌字符串
            verify_exp: 是否验证过期时间，默认为True
            
        Returns:
            dict: 包含验证结果的字典
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": verify_exp}
            )
            return {
                "success": True,
                "payload": payload
            }
        except jwt.ExpiredSignatureError:
            return {
                "success": False,
                "error": "Invalid token: Signature has expired."
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid token: {str(e)}"
            }

    def create_refresh_token(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建刷新令牌"""
        try:
            expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
            token_data = {
                **data,
                "exp": expire.timestamp(),
                "token_type": "refresh",
                "iat": datetime.utcnow().timestamp()
            }
            token = jwt.encode(
                token_data,
                self.secret_key,
                algorithm=self.algorithm
            )
            
            # 使用 add_token 方法来正确管理令牌
            self.add_token(
                token=token,
                username=data["username"],
                user_id=data["user_id"],
                expire_time=timedelta(days=self.refresh_token_expire_days),
                token_type="refresh",
                device_id=data.get("device_id", "default"),
                device_name=data.get("device_name", "Default Device")
            )
            
            return {
                "success": True,
                "token": token
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
            
            to_encode = data.copy()
            to_encode["token_type"] = "access"
            
            # 使用实例变量而不是全局变量
            current_time = datetime.utcnow()
            expire = current_time + timedelta(minutes=self.access_token_expire_minutes)
            
            to_encode.update({
                "iat": current_time.timestamp(),
                "exp": expire.timestamp(),
                "token_type": "access",
                "device_id": device_id,
                "device_name": device_name
            })
            
            # 创建JWT
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            # 添加令牌��管理器
            token = Token(
                token=encoded_jwt,
                username=data["username"],
                user_id=data["user_id"],
                expire=expire,
                token_type="access",
                device_id=device_id,
                device_name=device_name
            )
            self._access_tokens[encoded_jwt] = token
            
            return {
                "success": True,
                "token": encoded_jwt
            }
        except Exception as e:
            print(f">>> 创建访问令牌失败: {e}")
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
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        result = self.pwd_context.verify(plain_password, hashed_password)
        return {
            "success": result,
            "error": None if result else "Password Not Correct"
        }

    def validate_password(self, password: str) -> Dict[str, Any]:
        """验证密码强度"""
        if len(password) < 8:
            return {
                "success": False,
                "error": "密码长度必须至少为8个字符"
            }
        if not re.search(r"[A-Z]", password):
            return {
                "success": False,
                "error": "密码必须包含至少一个大写字母"
            }
        if not re.search(r"[a-z]", password):
            return {
                "success": False,
                "error": "密码必须包含至少一个小写字母"
            }
        if not re.search(r"\d", password):
            return {
                "success": False,
                "error": "密码必须包含至少一个数字"
            }
        return {
            "success": True,
            "error": None
        }

    def validate_email(self, email: str) -> Dict[str, Any]:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return {
                "success": False,
                "error": "邮箱格式无效"
            }
        return {
            "success": True,
            "error": None
        }

    def validate_username(self, username: str) -> Dict[str, Any]:
        """验证用户名格式"""
        if not username:
            return {
                "success": False,
                "error": "用户名不能为空"
            }
            
        if len(username) < 3 or len(username) > 32:
            return {
                "success": False,
                "error": "用户名长度必须在3到32个字符之间"
            }
            
        if not username[0].isalpha():
            return {
                "success": False,
                "error": "用户名必须以字母开头"
            }
            
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            return {
                "success": False,
                "error": "用户名只能包含字母、数字和下划线"
            }
            
        return {
            "success": True,
            "error": None
        }

    def invalidate_access_token(self, token: str) -> dict:
        """撤销单个访问令牌"""
        try:
            verify_result = self.verify_jwt(token, verify_exp=False)  # 允许验证过期令牌
            if not verify_result["success"]:
                return verify_result
            
            # 从内存中移除令牌
            if self._remove_access_token(token):
                return {
                    "success": True,
                    "message": "Access token invalidated successfully"
                }
            
            return {
                "success": False,
                "error": "Access token not found"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to invalidate access token: {str(e)}"
            }

    def invalidate_refresh_token(self, token: str) -> dict:
        """撤销单个刷新令牌"""
        try:
            verify_result = self.verify_jwt(token)
            if not verify_result["success"]:
                return verify_result
            
            user_id = verify_result["payload"].get("user_id")
            if not user_id:
                return {
                    "success": False,
                    "error": "Token missing user_id"
                }
            
            # 获取用户的令牌存储
            storage = self._storage.get(owner_id=user_id)
            if not storage or not isinstance(storage, TokenStorage):
                return {
                    "success": False,
                    "error": "No tokens found for user"
                }
            
            # 找到并移除匹配的令牌
            original_count = len(storage.tokens)
            storage.tokens = [t for t in storage.tokens if t.token != token]
            
            # 如果令牌数量变化了，说明找到并移除了令牌
            if len(storage.tokens) < original_count:
                # 更新存储
                self._storage.set(value=storage, owner_id=user_id)
                return {
                    "success": True,
                    "message": "Refresh token invalidated successfully"
                }
            
            return {
                "success": False,
                "error": "Refresh token not found"
            }
            
        except Exception as e:
            print(f"Error invalidating refresh token: {e}")
            return {
                "success": False,
                "error": f"Failed to invalidate refresh token: {str(e)}"
            }

    def invalidate_user_access_tokens(self, user_id: str) -> dict:
        """撤销用户的所有访问令牌"""
        try:
            # 创建副本以避免在迭代时修改典
            tokens_to_remove = [
                token for token, token_obj in list(self._access_tokens.items())
                if token_obj.user_id == user_id
            ]
            
            removed_count = 0
            for token in tokens_to_remove:
                if self._remove_access_token(token):
                    removed_count += 1
            
            return {
                "success": True,
                "message": f"Removed {removed_count} access tokens"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to invalidate user access tokens: {str(e)}"
            }

    def invalidate_user_refresh_tokens(self, user_id: str) -> dict:
        """撤销用户的所有刷新令牌
        
        Args:
            user_id: 用户ID
        """
        try:
            # 直接获取用户的��牌存储
            storage = self._storage.get(owner_id=user_id)
            if not storage:
                return {
                    "success": True,
                    "message": "No tokens found"
                }
            
            if not isinstance(storage, TokenStorage):
                storage = TokenStorage(tokens=[])
            
            # 获取令牌数量
            token_count = len(storage.tokens)
            
            # 清空令牌存储
            storage.tokens = []
            self._storage.set(value=storage, owner_id=user_id)
            
            return {
                "success": True,
                "message": f"Removed {token_count} refresh tokens"
            }
            
        except Exception as e:
            print(f"Error invalidating user refresh tokens: {e}")
            return {
                "success": False,
                "error": f"Failed to invalidate user refresh tokens: {str(e)}"
            }

    def invalidate_all_user_tokens(self, user_id: str) -> dict:
        """撤销用户的所有令牌"""
        try:
            # 1. 撤销访问令牌
            access_result = self.invalidate_user_access_tokens(user_id)
            if not access_result["success"]:
                return access_result
            
            # 2. 撤销刷新令牌
            refresh_result = self.invalidate_user_refresh_tokens(user_id)
            if not refresh_result["success"]:
                return refresh_result
            
            # 保持息格式一致
            access_count = int(access_result["message"].split()[1])
            refresh_count = int(refresh_result["message"].split()[1])
            
            return {
                "success": True,
                "message": f"Removed {access_count} access tokens, {refresh_count} refresh tokens"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to invalidate all user tokens: {str(e)}"
            }

    def list_user_devices(self, token: str) -> Dict[str, Any]:
        """列出用户的所有已登录设备"""
        print("\n=== 处理列出设备请求 ===")
        try:
            # 1. 验证令牌
            print(f">>> 验证令牌: {token[:30]}...")
            verify_result = self.verify_jwt(token)
            print(f">>> 验证结果: {verify_result}")
            if not verify_result["success"]:
                return verify_result
            
            # 2. 获取用户信息
            payload = verify_result["payload"]
            user_id = payload.get("user_id")
            if not user_id:
                error_msg = "Invalid token: missing user_id"
                print(f">>> 错误: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            current_device = payload.get("device_id", "default")
            print(f">>> 当前设备: {current_device}")
            
            # 3. 获取存储的令牌
            storage = self._storage.get(owner_id=user_id)
            print(f">>> 获取到的存储: {storage}")
            if not storage or not isinstance(storage, TokenStorage):
                print(">>> 未找到令牌存储，返回空列表")
                return {
                    "success": True,
                    "devices": []
                }
            
            # 4. 处理设备列表
            valid_tokens = [t for t in storage.tokens if not t.is_expired()]
            print(f">>> 有效令牌数量: {len(valid_tokens)}")
            
            # 5. 构建设备信息
            device_map = {}
            for token in valid_tokens:
                device_info = {
                    "device_id": token.device_id,
                    "device_name": token.device_name,
                    "last_active": token.expire.isoformat(),
                    "is_current": token.device_id == current_device
                }
                device_map[token.device_id] = device_info
                print(f">>> 添加设备信息: {device_info}")
            
            result = {
                "success": True,
                "devices": list(device_map.values())
            }
            print(f">>> 返回结果: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Failed to list devices: {str(e)}"
            print(f">>> 错误: {error_msg}")
            print(f">>> 异常详情: {e}")
            return {
                "success": False,
                "error": error_msg
            }

    def login(self, user_dict: Dict[str, Any], password: str, password_hash: str, 
             device_id: str, device_name: str) -> Dict[str, Any]:
        """用户登录"""
        print("\n=== 处理登录请求 ===")
        print(f">>> 输入参数:")
        print(f"  - user_dict: {user_dict}")
        print(f"  - device_id: {device_id}")
        print(f"  - device_name: {device_name}")
        
        # 1. 类型检查
        if not isinstance(user_dict, dict):
            error_msg = f"Invalid user_dict type: expected dict, got {type(user_dict)}"
            print(f">>> 错误: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        
        # 2. 必要字段检查
        required_fields = ["username", "user_id"]
        missing_fields = []
        
        for field in required_fields:
            if field not in user_dict:
                missing_fields.append(field)
            elif not user_dict[field]:
                missing_fields.append(f"{field} (empty)")
        
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            print(f">>> 错误: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        
        print(">>> 字段验证通过")
        
        # 3. 密码验证
        verify_result = self.verify_password(password, password_hash)
        if not verify_result["success"]:
            print(f">>> 密码验证失败: {verify_result['error']}")
            return verify_result
        
        print(">>> 密码验证通过")
        
        # 4. 准备令牌数据
        token_data = {
            **user_dict,
            "device_id": device_id,
            "device_name": device_name
        }
        
        # 5. 创建令牌
        print(">>> 开始创建令牌")
        access_token_result = self.create_access_token(token_data)
        refresh_token_result = self.create_refresh_token(token_data)
        
        if not access_token_result["success"] or not refresh_token_result["success"]:
            error = access_token_result.get("error") or refresh_token_result.get("error")
            print(f">>> 令牌创建失败: {error}")
            return {
                "success": False,
                "error": error
            }
        
        print(">>> 登录成功")
        return {
            "success": True,
            "access_token": access_token_result["token"],
            "refresh_token": refresh_token_result["token"],
            "token_type": "bearer"
        }

    def logout_device(self, token: str) -> Dict[str, Any]:
        """退出指定设备"""
        print("\n=== 处理设备登出请求 ===")
        try:
            # 1. 验证令牌（允许过期的令牌）
            print(f">>> 验证令牌: {token[:30]}...")
            verify_result = self.verify_jwt(token, verify_exp=False)  # 不验证过期时间
            print(f">>> 验证结果: {verify_result}")
            if not verify_result["success"]:
                return verify_result
            
            # 2. 获取令牌信息
            payload = verify_result["payload"]
            user_id = payload.get("user_id")
            device_id = payload.get("device_id")
            
            if not user_id or not device_id:
                error_msg = "Invalid token: missing user_id or device_id"
                print(f">>> 错误: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            print(f">>> 用户ID: {user_id}, 设备ID: {device_id}")
            
            # 3. 移除访问令牌
            print(">>> 移除访问令牌")
            access_tokens_to_remove = []
            for t, token_obj in self._access_tokens.items():
                if (token_obj.user_id == user_id and 
                    token_obj.device_id == device_id):
                    access_tokens_to_remove.append(t)
            
            for t in access_tokens_to_remove:
                self._access_tokens.pop(t, None)
            
            print(f">>> 移除了 {len(access_tokens_to_remove)} 个访问令牌")
            
            # 4. 移除刷新令牌
            print(">>> 移除刷新令牌")
            storage = self._storage.get(owner_id=user_id)
            if storage and isinstance(storage, TokenStorage):
                original_count = len(storage.tokens)
                storage.tokens = [
                    t for t in storage.tokens 
                    if t.device_id != device_id
                ]
                removed_count = original_count - len(storage.tokens)
                print(f">>> 移除了 {removed_count} 个刷新令牌")
                
                # 更新存储
                self._storage.set(value=storage, owner_id=user_id)
            
            return {
                "success": True,
                "message": f"Device {device_id} logged out successfully"
            }
            
        except Exception as e:
            error_msg = f"Logout failed: {str(e)}"
            print(f">>> 错误: {error_msg}")
            print(f">>> 异常详情: {e}")
            return {
                "success": False,
                "error": error_msg
            }

    def _is_token_revoked(self, token: str) -> bool:
        """检查令牌是否已被撤销
        
        Args:
            token: 要检查的令牌
            
        Returns:
            bool: 如果令牌被撤销返回True，否则返回False
        """
        try:
            # 解码令牌获取信息
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            token_type = payload.get("token_type", "access")
            user_id = payload.get("user_id")
            device_id = payload.get("device_id", "default")
            
            if token_type == "access":
                # 检查访问令牌是否在内存中
                return token not in self._access_tokens
            else:
                # 检查刷新令牌是否在存储中
                storage = self._storage.get(owner_id=user_id)
                if not storage or not isinstance(storage, TokenStorage):
                    return True
                    
                # 检查是否存在匹配的有效令牌
                return not any(
                    t.token == token and 
                    t.device_id == device_id and 
                    not t.is_expired()
                    for t in storage.tokens
                )
                
        except Exception as e:
            print(f"Error checking token revocation: {e}")
            return True  # 如有任何误，视为已撤销
