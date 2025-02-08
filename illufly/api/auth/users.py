from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime

from ...rocksdict import IndexedRocksDB
from ..result import Result
from .models import User, UserRole

import secrets
import string

__ADMIN_USER_ID__ = "admin"
__ADMIN_USERNAME__ = "admin"
__ADMIN_PASSWORD__ = "admin"

__USER_MODEL_NAME__ = "user"

class UsersManager:
    """用户管理器

    管理用户注册、登录、密码重置、角色管理等操作；
    """
    def __init__(self, db: IndexedRocksDB):
        """初始化用户管理器"""
        self._db = db
        self._db.register_model(__USER_MODEL_NAME__, User)
        self._db.register_index(__USER_MODEL_NAME__, "username")
        self._db.register_index(__USER_MODEL_NAME__, "email")
        self._db.register_index(__USER_MODEL_NAME__, "mobile")

        # 初始化管理员用户
        self.ensure_admin_user()

    def get_user(self, user_id: str) -> Optional[User]:
        """通过ID获取用户对象"""
        user = self._db[user_id]
        if not user:
            return None
        return User(**user)

    def get_user_info(self, user_id: str, include_sensitive: bool = False) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        user = self.get_user(user_id)
        if not user:
            return None
        return user.model_dump(exclude={"password_hash"} if not include_sensitive else {})

    def create_user(self, user: User) -> Result[Tuple[User, Optional[str]]]:
        """创建新用户"""
        if self._db.items_with_indexes(__USER_MODEL_NAME__, field_path="username", field_value=user.username):
            return Result.fail("用户已存在")
        
        self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
        return Result.ok(data=(user, None))

    def verify_password(self, username: str, password: str) -> Result[Dict[str, Any]]:
        """验证用户密码"""
        try:
            users = self._db.values_with_indexes(__USER_MODEL_NAME__, field_path="username", field_value=username)
            if not users:
                return Result.fail("用户不存在")
            
            user = User(**users[0])

            # 验证密码
            if not user.verify_password(password):
                return Result.fail("密码错误")

            require_password_change = (
                user.require_password_change or 
                user.is_password_expired()
            )

            user_dict = user.model_dump(exclude={"password_hash"})
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
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            user.roles = {UserRole(role) for role in roles}
            self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
            return Result.ok()
        except ValueError:
            return Result.fail("无效的角色值")

    def update_user(self, user_id: str, **kwargs) -> Result[None]:
        """更新用户信息"""
        if not User.can_update_field(list(kwargs.keys())):
            return Result.fail("提交的部份字段不允许更新")

        try:
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            user_data = user.model_dump()
            user_data.update(kwargs)
            updated_user = User(**user_data)
            self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, updated_user)
            return Result.ok()

        except Exception as e:
            return Result.fail(f"更新用户信息失败: {str(e)}")

    def delete_user(self, user_id: str) -> Result[None]:
        """删除用户"""
        try:
            if not self._db.delete(user_id):
                return Result.fail("用户不存在")
            return Result.ok()
        except Exception as e:
            return Result.fail(f"删除用户失败: {str(e)}")

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户"""
        users = []
        for user_id in self._db.iter_model_keys(__USER_MODEL_NAME__):
            if user_dict := self._db[user_id]:
                users.append(User(**user_dict))
        return users
    
    def change_password(self, user_id: str, old_password: str, new_password: str) -> Result[None]:
        """修改用户密码"""
        try:
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            # 验证旧密码
            if not user.verify_password(old_password):
                return Result.fail("旧密码错误")

            return self.reset_password(user_id, new_password)

        except Exception as e:
            print(f"修改用户密码失败: {str(e)}")
            return Result.fail(f"修改用户密码失败: {str(e)}")

    def reset_password(self, user_id: str, new_password: str) -> Dict[str, Any]:
        """不经过验证，直接重置用户密码（管理员功能）"""
        try:
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            # 对新密码进行哈希处理
            user.password_hash = User.hash_password(new_password)
            user.last_password_change = datetime.now()
            user.require_password_change = True            
            self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
            return Result.ok()

        except Exception as e:
            return Result.fail(f"重置用户密码失败: {str(e)}")

    def get_user_by_username(self, username: str) -> Optional[User]:
        """通过用户名获取用户"""
        users = self._db.find({"username": username})
        if not users:
            return None
        return users[0]

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        users = self._db.find({"email": email})
        if not users:
            return None
        return users[0]

    def ensure_admin_user(self) -> None:
        """确保管理员用户存在"""
        try:
            admin = self._db.get(__ADMIN_USER_ID__)
            if not admin:
                self.create_user(
                    user_id=__ADMIN_USER_ID__,
                    username=__ADMIN_USERNAME__,
                    password=__ADMIN_PASSWORD__,
                    roles=[UserRole.ADMIN],
                    require_password_change=False
                )
                
        except Exception as e:
            raise
