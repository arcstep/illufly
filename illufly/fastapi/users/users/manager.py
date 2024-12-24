from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
from pathlib import Path
from passlib.context import CryptContext

from ....io import ConfigStoreProtocol, FileConfigStore
from ...result import Result
from ..tokens import TokensManager
from ..invite import InviteCodeManager
from .models import User, UserRole

import secrets
import string
import re

from ....config import get_env
__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")
__USER_CONFIG_FILENAME__ = "profile.json"
__ADMIN_USER_ID__ = "admin"

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
                filename=__USER_CONFIG_FILENAME__,
                data_class=User,
                serializer=lambda user: user.to_dict(include_sensitive=True)
            )
        self._storage = storage

        # 初始化密码加密上下文
        self.hash_method = get_env("HASH_METHOD")
        if self.hash_method not in ["argon2", "bcrypt", "pbkdf2_sha256"]:
            raise ValueError(f"Unsupported hash method: {self.hash_method}")
        
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

        # 初始化管理员用户
        self.ensure_admin_user()

    def hash_password(self, password: str) -> Result[str]:
        """对密码进行哈希处理"""
        try:
            return Result.ok(data=self.pwd_context.hash(password))
        except Exception as e:
            return Result.fail(f"密码哈希处理失败: {str(e)}")

    def get_user(self, user_id: str) -> Optional[User]:
        """通过ID获取用户对象"""
        return self._storage.get(owner_id=user_id)

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
    ) -> Result[Tuple[User, Optional[str]]]:
        """创建新用户"""
        try:
            username = username or email

            # 验证用户名
            username_validation = self.validate_username(username)
            if not username_validation.success:
                return Result.fail(username_validation.error)
            
            # 验证邮箱
            if email:
                email_validation = self.validate_email(email)
                if not email_validation.success:
                    return Result.fail(email_validation.error)
            
            # 验证密码
            if password:
                password_validation = self.validate_password(password)
                if not password_validation.success:
                    return Result.fail(password_validation.error)

            # 检查用户名或邮箱是否已存在        
            if self._storage.has_duplicate({"username": username}):
                return Result.fail("用户名已存在")

            if self._storage.has_duplicate({"email": email}):
                return Result.fail("邮箱已存在")

            # 生成随机密码（如果没有提供）
            generated_password = None
            if not password:
                generated_password = self.generate_random_password()
                password = generated_password

            # 对密码进行哈希处理
            hash_result = self.hash_password(password)
            if not hash_result.success:
                return Result.fail(hash_result.error)

            # 创建新用户对象
            user = User(
                user_id=user_id,
                username=username,
                email=email,
                password_hash=hash_result.data,
                roles=set(roles or [UserRole.USER, UserRole.GUEST]),
                created_at=datetime.now(),
                require_password_change=require_password_change,
                last_password_change=datetime.now() if not require_password_change else None,
                password_expires_days=password_expires_days
            )
            
            # 保存用户数据
            try:
                self._storage.set(user, owner_id=user.user_id)
                return Result.ok(data=(user, generated_password))
            except Exception as e:
                return Result.fail(f"保存用户数据失败: {str(e)}")
            
        except Exception as e:
            return Result.fail(f"创建用户时发生错误: {str(e)}")

    def verify_user_password(self, username: str, password: str) -> Result[Dict[str, Any]]:
        """验证用户密码"""
        try:
            print(">>> verify_user_password: ", username, password)
            user = self.get_user_by_username(username)
            print(">>> user: ", user)
            if not user:
                return Result.fail("用户不存在")
            
            # 验证密码
            if not self.pwd_context.verify(password, user.password_hash):
                return Result.fail("密码错误")

            require_password_change = (
                user.require_password_change or 
                user.is_password_expired()
            )

            # 确保返回的用户对象中的roles是list类型
            user_dict = user.to_dict(include_sensitive=False)
            if "roles" in user_dict:
                user_dict["roles"] = list(user_dict["roles"])
            print(">>> user_dict: ", user_dict)

            return Result.ok(data={
                "require_password_change": require_password_change,
                "user": user_dict
            })
        except Exception as e:
            print(">>> verify_user_password error: ", str(e))
            return Result.fail(f"密码验证失败: {str(e)}")

    def update_user_roles(self, user_id: str, roles: List[str]) -> Result[None]:
        """更新用户角色"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return Result.fail("用户不存在")

            user_roles = {UserRole(role) for role in roles}
            user.roles = user_roles
            self._storage.set(user, owner_id=user_id)
            return Result.ok()
        except ValueError:
            return Result.fail("无效的角色值")

    def update_user(self, user_id: str, **kwargs) -> Result[None]:
        """更新用户信息"""
        try:    
            user = self._storage.get(owner_id=user_id)
            if not user:
                return Result.fail("用户不存在")

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self._storage.set(user, owner_id=user_id)
            return Result.ok()
        except Exception as e:
            return Result.fail(f"更新用户信息失败: {str(e)}")

    def delete_user(self, user_id: str) -> Result[None]:
        """删除用户"""
        try:
            if not self._storage.delete(owner_id=user_id):
                return Result.fail("用户不存在")
            return Result.ok()
        except Exception as e:
            return Result.fail(f"删除用户失败: {str(e)}")

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        users = []
        for user_id in self._storage.list_owners():
            if user := self._storage.get(owner_id=user_id):
                users.append(user.to_dict(include_sensitive=False))
        return users
    
    def change_password(self, user_id: str, old_password: str, new_password: str) -> Result[None]:
        """修改用户密码"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return Result.fail("用户不存在")

            # 验证旧密码
            verify_result = self.pwd_context.verify(old_password, user.password_hash)
            if not verify_result:
                return Result.fail("旧密码错误")

            # 对新密码进行哈希处理
            hash_result = self.hash_password(new_password)
            if not hash_result.success:
                return Result.fail(hash_result.error)

            user.password_hash = hash_result.data
            user.last_password_change = datetime.now()
            user.require_password_change = False
            
            self._storage.set(user, owner_id=user_id)
            return Result.ok()
        except Exception as e:
            print(f"修改用户密码失败: {str(e)}")
            return Result.fail(f"修改用户密码失败: {str(e)}")

    def reset_password(self, user_id: str, new_password: str, admin_required: bool = True) -> Dict[str, Any]:
        """重置用户密码（管理员功能）"""
        try:
            user = self._storage.get(owner_id=user_id)
            if not user:
                return Result.fail("用户不存在")

            # 对新密码进行哈希处理
            hash_result = self.hash_password(new_password)
            if not hash_result["success"]:
                return Result.fail(hash_result.error)
        
            user.password_hash = hash_result["hash"]
            user.last_password_change = datetime.now()
            user.require_password_change = True
            
            self._storage.set(user, owner_id=user_id)
            return Result.ok()
        except Exception as e:
            return Result.fail(f"重置用户密码失败: {str(e)}")

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
        users = self._storage.find({"username": username})
        if not users:
            return None
        return users[0]

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        users = self._storage.find({"email": email})
        if not users:
            return None
        return users[0]

    def ensure_admin_user(self) -> None:
        """确保管理员用户存在"""
        try:
            admin = self._storage.get(__ADMIN_USER_ID__)
            if not admin:
                admin_id = __ADMIN_USER_ID__
                self.create_user(
                    username=get_env("FASTAPI_USERS_ADMIN_USERNAME"),
                    password=get_env("FASTAPI_USERS_ADMIN_PASSWORD"),
                    email=get_env("FASTAPI_USERS_ADMIN_EMAIL"),
                    user_id=admin_id,
                    roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER, UserRole.GUEST],
                    require_password_change=False
                )
                
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
            return Result.fail("密码长度必须至少为8个字符")
        
        if not re.search(r"[A-Z]", password):
            return Result.fail("密码必须包含至少一个大写字母")
        
        if not re.search(r"[a-z]", password):
            return Result.fail("密码必须包含至少一个小写字母")
        
        if not re.search(r"\d", password):
            return Result.fail("密码必须包含至少一个数字")
        
        return Result.ok()

    def validate_email(self, email: str) -> Dict[str, Any]:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return Result.fail("邮箱格式无效")
        
        return Result.ok()

    def validate_username(self, username: str) -> Dict[str, Any]:
        """验证用户名格式"""
        if not username:
            return Result.fail("用户名不能为空")
            
        if len(username) < 3 or len(username) > 32:
            return Result.fail("用户名长度必须在3到32个字符之间")
            
            
        if not username[0].isalpha():
            return Result.fail("用户名必须以字母开头")
            
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            return Result.fail("用户名只能包含字母、数字和下划线")
            
        return Result.ok()
