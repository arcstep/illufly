from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
import secrets
import string
from pathlib import Path
from ..common import StorageProtocol, FileStorage
from ..auth.utils import verify_password, hash_password
from .models import User, UserRole

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
                use_id_subdirs=True  # 改用 ID 子目录模式
            )
        self._storage = storage
        self._admin_ids = set()  # 存储管理员ID而不是用户名

        # 检查并创建管理员账户
        admin_email = "admin@illufly.com"
        admin = self.get_user_by_username("admin")
        if not admin:
            result = self.create_user(
                username="admin", 
                password="admin",
                email=admin_email, 
                roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER, UserRole.GUEST],
                require_password_change=False
            )
            if result["success"]:
                self._admin_ids.add(result["user"].user_id)

    def get_user(self, user_id: str, requester_id: str) -> Optional[User]:
        """通过ID获取用户对象"""
        if not self.can_access_user(user_id, requester_id):
            return None
        return self._storage.get(user_id, owner_id=user_id)

    def can_access_user(self, user_id: str, requester_id: str) -> bool:
        """检查是否有权限访问用户数据"""
        return requester_id == user_id or requester_id in self._admin_ids

    def get_user_info(self, user_id: str, include_sensitive: bool = False) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        user = self._storage.get(user_id, owner_id=user_id)
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
        """创建新用户
        Returns:
            Dict 包含以下字段：
            - success: bool 是否成功
            - generated_password: Optional[str] 生成的随机密码（如果有）
            - user: Optional[User] 创建的用户对象
            - error: Optional[str] 错误信息（如果有）
        """
        username = username or email

        user = self._storage.get(user_id, owner_id=user_id)
        if not user:
            return None

        # 检查用户名是否已存在
        if self.get_user_by_username(username):
            return {
                "success": False,
                "generated_password": None,
                "user": None,
                "error": "Username already exists"
            }

        # 检查邮箱是否已被使用
        if self.get_user_by_email(email):
            return {
                "success": False,
                "generated_password": None,
                "user": None,
                "error": "Email already exists"
            }

        generated_password = None
        if not password:
            generated_password = self.generate_random_password()
            password = generated_password

        user = User(
            user_id=user_id,
            username=username,
            email=email,
            password_hash=hash_password(password),
            roles=set(roles or [UserRole.USER, UserRole.GUEST]),
            created_at=datetime.now(),
            require_password_change=require_password_change,
            last_password_change=datetime.now() if not require_password_change else None,
            password_expires_days=password_expires_days
        )
        
        # 使用用户ID作为存储键和所有者ID
        self._storage.set(user.user_id, user, owner_id=user.user_id)
        
        return {
            "success": True,
            "generated_password": generated_password,
            "user": user,
            "error": None
        }

    def verify_user_password(self, username: str, password: str) -> Tuple[bool, bool]:
        """验证用户密码"""
        user = self.get_user_by_username(username)
        if not user:
            return False, False
        
        try:
            password_correct = verify_password(password, user.password_hash)
        except Exception as e:
            print(f"Password verification failed: {e}")
            return False, False

        need_change = (
            user.require_password_change or 
            user.is_password_expired()
        )
        
        return password_correct, need_change, user

    def update_user_roles(self, user_id: str, roles: List[str]) -> bool:
        """更新用户角色"""
        user = self._storage.get(user_id, owner_id=user_id)
        if not user:
            return False

        try:
            user_roles = {UserRole(role) for role in roles}
            user.roles = user_roles
            self._storage.set(user_id, user, owner_id=user_id)
            return True
        except ValueError:
            return False

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        users = []
        for user_id in self._storage.list_owners():
            if user := self._storage.get("profile", owner_id=user_id):
                users.append(user.to_dict(include_sensitive=False))
        return users

    def update_user(self, user_id: str, **kwargs) -> bool:
        """更新用户信息"""
        try:    
            user = self._storage.get(user_id, owner_id=user_id)
            if not user:
                return False

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self._storage.set(user_id, user, owner_id=user_id)
            return True
        except Exception as e:
            print(f"Error updating user: {e}")
            return False

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """修改用户密码"""
        try:
            user = self._storage.get(user_id, owner_id=user_id)
            if not user:
                return False

            # 验证旧密码
            if not verify_password(old_password, user.password_hash):
                return False

            user.password_hash = hash_password(new_password)
            user.last_password_change = datetime.now()
            user.require_password_change = False
            
            self._storage.set(user_id, user, owner_id=user_id)
            return True
        except Exception as e:
            print(f"Error changing password: {e}")
            return False

    def reset_password(self, user_id: str, new_password: str, admin_required: bool = True) -> bool:
        """重置用户密码（管理员功能）"""
        try:
            user = self._storage.get("profile", owner_id=user_id)
            if not user:
                return False
        
            user.password_hash = hash_password(new_password)
            user.last_password_change = datetime.now()
            user.require_password_change = True
            
            self._storage.set("profile", user, owner_id=user_id)
            return True
        except Exception as e:
            print(f"Error resetting password: {e}")
            return False

    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        return self._storage.delete(user_id, owner_id=user_id)

    def user_exists(self, user_id: str) -> bool:
        """检查用户是否存在"""
        return self._storage.get(user_id, owner_id=user_id) is not None

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
        for user_id in self._storage.list_owners():
            if user := self._storage.get(user_id, owner_id=user_id):
                if user.username == username:
                    return user
        return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        for user_id in self._storage.list_owners():
            if user := self._storage.get(user_id, owner_id=user_id):
                if user.email == email:
                    return user
        return None

