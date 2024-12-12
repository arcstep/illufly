from typing import Dict, Any, Optional, Set, Union, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Response
import re
from pathlib import Path

from ...config import get_env
from ..common import ConfigStoreProtocol, FileConfigStore
from .dependencies import AuthDependencies

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

@dataclass
class Token:
    """令牌数据模型"""
    token: str
    username: str  # 用于显示
    user_id: str   # 用于存储
    expire: datetime
    token_type: str  # "access" 或 "refresh"
    
    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "username": self.username,
            "user_id": self.user_id,
            "expire": self.expire.isoformat(),
            "token_type": self.token_type
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'Token':
        return Token(
            token=data["token"],
            username=data["username"],
            user_id=data["user_id"],
            expire=datetime.fromisoformat(data["expire"]),
            token_type=data["token_type"]
        )
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expire

class AuthManager:
    def __init__(self, storage: Optional[ConfigStoreProtocol[Token]] = None, dependencies: Optional[AuthDependencies] = None):
        """初始化令牌管理器
        Args:
            storage: 令牌存储实现，如果为None则使用默认的文件存储
        """
        if storage is None:
            # 为令牌创建存储实例，使用与用户相同的子目录结构
            storage = FileConfigStore[Token](
                data_dir=Path(__USERS_PATH__),
                filename="tokens.json",  # 在用户子目录下的令牌文件
                serializer=lambda token: token.to_dict(),
                deserializer=Token.from_dict,
                use_id_subdirs=True  # 使用子目录模式
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

    def add_token(self, token: str, username: str, user_id: str, expire_time: timedelta, token_type: str) -> None:
        """添加令牌
        
        Args:
            token: 令牌字符串
            username: 用户名
            user_id: 用户ID
            expire_time: 过期时间
            token_type: 令牌类型 ("access" 或 "refresh")
        """
        try:
            expire = datetime.utcnow() + expire_time
            token_obj = Token(
                token=token,
                username=username,
                user_id=user_id,
                expire=expire,
                token_type=token_type
            )
            
            if token_type == "access":
                self._clear_expired_access_tokens()
                self._access_tokens[token] = token_obj
            else:  # refresh token
                try:
                    # 存储新的刷新令牌
                    self._storage.set(token, token_obj, owner_id=user_id)
                except Exception as e:
                    print(f"Error storing refresh token: {e}")
                    raise
            
        except Exception as e:
            print(f"Error adding token: {e}")
            raise

    def is_token_valid(self, token: str, token_type: str) -> dict:
        """检查令牌是否有效
        
        Args:
            token: 令牌字符串
            token_type: 令牌类型 ("access" 或 "refresh")
            
        Returns:
            dict: 包含令牌是否有效的字典
        """
        try:
            # 首先验证JWT格式
            verify_result = self.verify_jwt(token)
            if not verify_result["success"]:
                return verify_result
            
            # 使用user_id而不是username
            user_id = verify_result["payload"].get("user_id")
            if not user_id:
                return {
                    "success": False,
                    "error": "Missing user_id in token"
                }
            
            if token_type == "access":
                # 检查访问令牌
                stored_token = self._access_tokens.get(token)
            else:
                # 检���刷新令牌，使用user_id作为owner_id
                stored_token = self._storage.get(token, owner_id=user_id)
            
            if not stored_token:
                return {
                    "success": False,
                    "error": "Token not found"
                }
            
            if stored_token.is_expired():
                return {
                    "success": False,
                    "error": "Token has expired"
                }
            
            return {
                "success": True,
                "error": None
            }
            
        except Exception as e:
            print(f">>> 验证令牌时出错: {e}")
            return {
                "success": False,
                "error": str(e)
            }

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

    def verify_jwt(self, token: str) -> Dict[str, Any]:
        """验证JWT令牌"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return {
                "success": True,
                "payload": payload,
                "error": None
            }
        except JWTError as e:
            return {
                "success": False,
                "payload": None,
                "error": str(e)
            }

    def create_refresh_token(self, data: dict) -> dict:
        """创建刷新令牌"""
        try:
            print(">>> 开始创建刷新令牌")
            expire_days = get_env("REFRESH_TOKEN_EXPIRE_DAYS")
            to_encode = data.copy()
            expire = datetime.utcnow() + timedelta(days=expire_days)
            to_encode.update({"exp": expire})
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            user_id = data.get('user_id')
            username = data.get('username')
            if not user_id or not username:
                print(">>> 令牌数据中缺少必要信息")
                return {
                    "success": False,
                    "error": "Missing user information in token data"
                }
            
            # 创建令牌对象
            token_obj = Token(
                token=encoded_jwt,
                username=username,
                user_id=user_id,
                expire=expire,
                token_type="refresh"
            )
            
            print(f">>> 正在存储刷新令牌，用户ID: {user_id}")
            self._storage.set(encoded_jwt, token_obj, owner_id=user_id)
            print(">>> 刷新令牌创建成功")
            
            return {
                "success": True,
                "token": encoded_jwt
            }
        except Exception as e:
            print(f">>> 创建刷新令牌失败: {e}")
            return {
                "success": False,
                "error": f"Failed to create refresh token: {str(e)}"
            }

    def create_access_token(self, data: dict) -> dict:
        """创建访问令牌"""
        try:
            try:
                expire_minutes = int(get_env("ACCESS_TOKEN_EXPIRE_MINUTES"))
            except:
                expire_minutes = 30
            
            to_encode = data.copy()
            expire = datetime.utcnow() + timedelta(minutes=expire_minutes)
            to_encode.update({"exp": expire})
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            
            user_id = data.get('user_id')
            username = data.get('username')
            if not user_id or not username:
                return {
                    "success": False,
                    "error": "Missing user information in token data"
                }
            
            # 使用更新后的add_token方法
            self.add_token(
                token=encoded_jwt,
                username=username,
                user_id=user_id,
                expire_time=timedelta(minutes=expire_minutes),
                token_type="access"
            )
            
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

    def invalidate_token(self, token: str) -> dict:
        """使单个令牌失效
        
        Args:
            token (str): 要使失效的令牌
            
        Returns:
            dict: 包含操作结果的字典
        """
        try:
            # 1. 验证JWT获用户名
            verify_result = self.verify_jwt(token)
            if not verify_result["success"]:
                return {
                    "success": False,
                    "error": f"Invalid token: {verify_result['error']}"
                }
            
            username = verify_result["payload"].get("username")
            if not username:
                return {
                    "success": False,
                    "error": "Token payload missing username"
                }

            # 2. 尝试访问令牌缓存中移除
            if token in self._access_tokens:
                self._remove_access_token(token)
                return {
                    "success": True,
                    "message": "Access token invalidated successfully"
                }
                
            # 3. 尝试从刷新令牌存储中移除
            stored_token = self._storage.get(token, owner_id=username)
            if stored_token:
                if self._storage.delete(token, owner_id=username):
                    return {
                        "success": True,
                        "message": "Refresh token invalidated successfully"
                    }
                
            # 4. 如果令牌不存在
            return {
                "success": False,
                "error": "Token not found in storage"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to invalidate token: {str(e)}"
            }

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """用户登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            Dict[str, Any]: 登录结果
        """
        print(f">>> 尝试登录用户: {username}")
        
        # 获取用户
        user = self.user_manager.get_user_by_username(username)
        if not user:
            print(">>> 用户不存在")
            return {
                "success": False,
                "error": "User not found"
            }
        
        # 验证密码
        verify_result = self.verify_password(password, user.password_hash)
        if not verify_result["success"]:
            print(">>> 密码验证失败")
            return {
                "success": False,
                "error": verify_result["error"]
            }
        
        # 创建令牌
        token_data = user.to_dict(include_sensitive=False)
        access_token_result = self.create_access_token(token_data)
        refresh_token_result = self.create_refresh_token(token_data)
        
        if not access_token_result["success"] or not refresh_token_result["success"]:
            print(">>> 创建令牌失败")
            return {
                "success": False,
                "error": access_token_result.get("error") or refresh_token_result.get("error")
            }
        
        print(">>> 登录成功")
        return {
            "success": True,
            "access_token": access_token_result["token"],
            "refresh_token": refresh_token_result["token"],
            "token_type": "bearer"
        }
