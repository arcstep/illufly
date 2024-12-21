from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from pathlib import Path

from ....io import ConfigStoreProtocol, FileConfigStore
from ..tokens import TokensManager
from ..invite import InviteCodeManager
from .models import User, UserRole

import secrets
import string
import re

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

class UsersManager:
    def __init__(
        self,
        tokens_manager: TokensManager = None,
        invite_manager: InviteCodeManager = None,
        storage: Optional[ConfigStoreProtocol] = None,
        config_store_path: str = None
    ):
        """初始化用户管理器
        Args:
            tokens_manager: 认证管理器
            storage: 存储实现，如果为None则使用默认的文件存储
        """
        self.tokens_manager = tokens_manager or TokensManager(config_store_path=config_store_path)
        self.invite_manager = invite_manager or InviteCodeManager(config_store_path=config_store_path)
        if storage is None:
            storage = FileConfigStore(
                data_dir=Path(config_store_path or __USERS_PATH__),
                filename="profile.json",
                data_class=User,
                serializer=lambda user: user.to_dict(include_sensitive=True),
                deserializer=User.from_dict,
            )
        self._storage = storage
        self._admin_ids = set()
        
        # 确保数据目录存在
        Path(__USERS_PATH__).mkdir(parents=True, exist_ok=True)
        
        # 初始化管理员用户
        self.ensure_admin_user()

    def get_user(self, user_id: str, requester_id: str) -> Optional[User]:
        """通过ID获取用户对象"""
        if not self.can_access_user(user_id, requester_id):
            return None
        return self._storage.get(owner_id=user_id)

    def can_access_user(self, user_id: str, requester_id: str) -> bool:
        """检查是否有权限访问用户数据"""
        return requester_id == user_id or requester_id in self._admin_ids

    def get_user_info(self, user_id: str, include_sensitive: bool = False) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        user = self._storage.get(owner_id=user_id)
        if not user:
            return None
        return user.to_dict(include_sensitive=include_sensitive)

    def create_user(
        self, 
        email: str,
        username: str = None,
        user_id: str = None,
        roles: List[str] = None, 
        password: str = None, 
        require_password_change: bool = True,
        password_expires_days: int = 90
    ) -> Dict[str, Any]:
        """创建新用户"""
        try:
            username = username or email

            # 检查用户名或邮箱是否已存在        
            if self._storage.has_duplicate({"username": username}):
                return {
                    "success": False,
                    "error": f"用户名已存在"
                }

            if self._storage.has_duplicate({"email": email}):
                return {
                    "success": False,
                    "error": f"邮箱已存在"
                }

            # 生成随机密码（如果没有提供）
            generated_password = None
            if not password:
                generated_password = self.generate_random_password()
                password = generated_password

            # 对密码进行哈希处理
            hash_result = self.tokens_manager.hash_password(password)
            if not hash_result["success"]:
                return {
                    "success": False,
                    "error": hash_result["error"]
                }

            # 创建新用户对象
            user = User(
                user_id=user_id,
                username=username,
                email=email,
                password_hash=hash_result["hash"],
                roles=set(roles or [UserRole.USER, UserRole.GUEST]),
                created_at=datetime.now(),
                require_password_change=require_password_change,
                last_password_change=datetime.now() if not require_password_change else None,
                password_expires_days=password_expires_days
            )
            
            # 保存用户数据
            try:
                self._storage.set(user, owner_id=user.user_id)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to save user data: {str(e)}",
                    "user": None,
                    "generated_password": None
                }
            
            return {
                "success": True,
                "generated_password": generated_password,
                "user": user,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error while creating user: {str(e)}",
                "user": None,
                "generated_password": None
            }

    def verify_user_password(self, username: str, password: str) -> Dict[str, Any]:
        """验证用户密码"""
        try:
            user = self.get_user_by_username(username)
            if not user:
                return {
                    "success": False, 
                    "require_password_change": False, 
                    "user": None,
                    "error": "User not found"
                }
            
            # 验证密码
            verify_result = self.tokens_manager.verify_password(password, user.password_hash)
            if not verify_result["success"]:
                return {
                    "success": False, 
                    "require_password_change": False, 
                    "user": None,
                    "error": verify_result["error"]
                }

            require_password_change = (
                user.require_password_change or 
                user.is_password_expired()
            )

            # 确保返回的用户对象中的roles是list类型
            user_dict = user.to_dict(include_sensitive=True)
            if "roles" in user_dict:
                user_dict["roles"] = list(user_dict["roles"])

            return {
                "success": True, 
                "require_password_change": require_password_change, 
                "user": user_dict,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "require_password_change": False,
                "user": None,
                "error": str(e)
            }

    def update_user_roles(self, user_id: str, roles: List[str]) -> Dict[str, Any]:
        """更新用户角色"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            user_roles = {UserRole(role) for role in roles}
            user.roles = user_roles
            self._storage.set(user, owner_id=user_id)
            return {
                "success": True,
                "error": None
            }
        except ValueError:
            return {
                "success": False,
                "error": "Invalid role value"
            }

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        users = []
        for user_id in self._storage.list_owners():
            if user := self._storage.get(owner_id=user_id):
                users.append(user.to_dict(include_sensitive=False))
        return users

    def update_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """更新用户信息"""
        try:    
            user = self._storage.get(owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self._storage.set(user, owner_id=user_id)
            return {
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def change_password(self, user_id: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """修改用户密码"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            # 验证旧密码
            verify_result = self.tokens_manager.verify_password(old_password, user.password_hash)
            if not verify_result["success"]:
                return {
                    "success": False,
                    "error": verify_result["error"]
                }

            # 对新密码进行哈希处理
            hash_result = self.tokens_manager.hash_password(new_password)
            if not hash_result["success"]:
                return {
                    "success": False,
                    "error": hash_result["error"]
                }

            user.password_hash = hash_result["hash"]
            user.last_password_change = datetime.now()
            user.require_password_change = False
            
            self._storage.set(user, owner_id=user_id)
            return {
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def reset_password(self, user_id: str, new_password: str, admin_required: bool = True) -> Dict[str, Any]:
        """重置用户密码（管理员功能）"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            # 对新密码进行哈希处理
            hash_result = self.tokens_manager.hash_password(new_password)
            if not hash_result["success"]:
                return {
                    "success": False,
                    "error": hash_result["error"]
                }
        
            user.password_hash = hash_result["hash"]
            user.last_password_change = datetime.now()
            user.require_password_change = True
            
            self._storage.set(user, owner_id=user_id)
            return {
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """删除用户"""
        try:
            if not self._storage.delete(owner_id=user_id):
                return {
                    "success": False,
                    "error": "User not found"
                }
            return {
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def user_exists(self, user_id: str) -> bool:
        """检查用户是否存在"""
        return self._storage.get(owner_id=user_id) is not None

    @staticmethod
    def generate_random_password(length: int = 12) -> str:
        """生成随机密码"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(length-2))
        password += secrets.choice(string.digits)
        password += secrets.choice("!@#$%^&*")
        password_list = list(password)
        secrets.SystemRandom().shuffle(password_list)
        return ''.join(password_list)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""       
        try:
            # 遍历所有用户ID
            owners = self._storage.list_owners()
            
            for user_id in owners:
                try:
                    # 使用user_id作为存储键和owner_id
                    user = self._storage.get(owner_id=user_id)
                    if user and user.username == username:  # 匹配username
                        return user
                except Exception as e:
                    continue
            return None
            
        except Exception as e:
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户
        
        Args:
            email: 用户邮箱
            
        Returns:
            Optional[User]: 找到的用户对象，如果不存在则返回 None
        """
        try:
            # 转换为小写进行比较
            email = email.lower()
            for user_id in self._storage.list_owners():
                if user := self._storage.get(owner_id=user_id):
                    # 同样转换为小写进行比较
                    if user.email.lower() == email:
                        return user
            return None
        except Exception as e:
            return None

    def verify_invite_code(self, invite_code: str) -> bool:
        """验证邀请码
        Args:
            invite_code: 待验证的邀请码
        Returns:
            bool: 邀请码是否有效
        """
        # TODO: 实现邀请码验证逻辑
        return {
            "success": True,
            "error": None
        }

    def ensure_admin_user(self) -> None:
        """确保管理员用户存在"""
        try:
            admin = self.get_user_by_username("admin")
            
            if not admin:
                # 使用固定的user_id作为存储键
                admin_id = "admin"
                self.create_user(
                    username="admin",  # 显示名称
                    password="admin",
                    email="admin@illufly.com",
                    user_id=admin_id,  # 存储键
                    roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER, UserRole.GUEST],
                    require_password_change=False
                )
            else:
                self._admin_ids.add(admin.user_id)  # 使用user_id而不是username
                
        except Exception as e:
            raise

    def validate_password(self, password: str) -> Dict[str, Any]:
        """验证密码强度
        
        要求：
        - 长度至少8个字符
        - 至少包含一个大写字母
        - 至少包含一个小写字母
        - 至少包含一个数字
        
        Args:
            password: 要验证的密码
            
        Returns:
            dict: 包含验证结果的字典
                - success: 是否通过验证
                - error: 未通过时的错误信息
        """
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