from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from .models import User, UserRole
import secrets
import string
from ..common import StorageProtocol, FileStorage
from pathlib import Path

class UserManager:
    def __init__(self, storage: Optional[StorageProtocol[User]] = None):
        """初始化用户管理器
        Args:
            storage: 存储实现，如果为None则使用默认的文件存储
        """
        if storage is None:
            storage = FileStorage[User](
                data_dir="__users__",
                filename="profile.json",
                serializer=lambda user: user.to_dict(include_sensitive=True),
                deserializer=User.from_dict,
                use_owner_subdirs=True  # 使用子目录模式
            )
        self._storage = storage
        self._admin_usernames = {"admin"}

        # 检查并创建管理员账户
        admin_email = "admin@illufly.com"
        if not self.get_user("admin", "admin"):
            self.create_user(
                username="admin", 
                password="admin",
                email=admin_email, 
                roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER, UserRole.GUEST],
                require_password_change=False
            )

    def get_user(self, username: str, requester: str) -> Optional[User]:
        """获取用户对象"""
        if not self._can_access_user(requester, username):
            return None
        return self._storage.get(username, owner=username)

    def _can_access_user(self, requester: str, target: str) -> bool:
        """检查是否有权限访问用户数据"""
        return requester == target or requester in self._admin_usernames

    def get_user_info(self, username: str, include_sensitive: bool = False) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        user = self._storage.get(username, owner=username)
        if not user:
            return None
        return user.to_dict(include_sensitive=include_sensitive)

    def create_user(
        self, 
        email: str,
        username: str = None, 
        roles: List[str] = None, 
        password: str = None, 
        require_password_change: bool = True,
        password_expires_days: int = 90
    ) -> Tuple[bool, Optional[str]]:
        """创建新用户"""
        username = username or email
        
        # 同时检查 username 是否存在
        if self.user_exists(username):
            return False, None
        
        # 同时检查 email 是否已被其他用户使用（如果需要的话）
        for existing_user in self.list_users("admin"):
            if existing_user.get("email") == email and existing_user.get("username") != username:
                return False, None

        generated_password = None
        if not password:
            generated_password = self.generate_random_password()
            password = generated_password

        user = User(
            username=username,
            email=email,
            password_hash=User.hash_password(password),
            roles=set(roles or [UserRole.USER]),
            created_at=datetime.now(),
            require_password_change=require_password_change,
            last_password_change=datetime.now() if not require_password_change else None,
            password_expires_days=password_expires_days
        )
        
        # 只使用 username 作为存储标识符
        self._storage.set(username, user, owner=username)
        return True, generated_password

    def verify_user_password(self, username: str, password: str) -> Tuple[bool, bool]:
        """验证用户密码"""
        user = self._storage.get(username, owner=username)
        if not user:
            return False, False
        
        password_correct = user.verify_password(password)
        need_change = (
            user.require_password_change or 
            user.is_password_expired()
        )
        
        return password_correct, need_change

    def update_user_roles(self, username: str, roles: List[str]) -> bool:
        """更新用户角色"""
        user = self._storage.get(username, owner=username)
        if not user:
            return False

        user.roles = set(roles)
        self._storage.set(username, user, owner=username)
        return True

    def list_users(self, requester: str) -> List[Dict[str, Any]]:
        """列出所有用户（不包含敏感信息）"""
        if requester not in self._admin_usernames:
            return []
        
        users = []
        # 遍历用户目录
        for user_dir in Path("__users__").iterdir():
            if user_dir.is_dir():
                username = user_dir.name
                if user := self._storage.get(username, owner=username):
                    users.append(user.to_dict(include_sensitive=False))
        return users

    def update_user(self, username: str, **kwargs) -> bool:
        """更新用户信息"""
        user = self._storage.get(username, owner=username)
        if not user:
            return False

        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        self._storage.set(username, user, owner=username)
        return True

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改用户密码"""
        user = self._storage.get(username, owner=username)
        if not user or not user.verify_password(old_password):
            return False
        
        user.password_hash = User.hash_password(new_password)
        user.last_password_change = datetime.now()
        user.require_password_change = False
        
        self._storage.set(username, user, owner=username)
        return True

    def reset_password(self, username: str, new_password: str, admin_required: bool = True) -> bool:
        """重置用户密码（管理员功能）"""
        user = self._storage.get(username, owner=username)
        if not user:
            return False
        
        user.password_hash = User.hash_password(new_password)
        user.last_password_change = datetime.now()
        user.require_password_change = True
        
        self._storage.set(username, user, owner=username)
        return True

    def delete_user(self, username: str) -> bool:
        """删除用户"""
        return self._storage.delete(username, owner=username)

    def user_exists(self, username: str) -> bool:
        """检查用户是否存在"""
        return self._storage.get(username, owner=username) is not None

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

