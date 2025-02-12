from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime

from ...rocksdb import IndexedRocksDB
from ..models import Result
from .models import User, UserRole

import secrets
import string
import logging

__ADMIN_USER_ID__ = "admin"
__ADMIN_USERNAME__ = "admin"
__ADMIN_PASSWORD__ = "admin"

__USER_MODEL_NAME__ = "user"

class UsersManager:
    """用户管理器

    管理用户注册、登录、密码重置、角色管理等操作；
    """
    def __init__(self, db: IndexedRocksDB, logger: logging.Logger = None):
        """初始化用户管理器"""
        self._logger = logger or logging.getLogger(__name__)

        self._db = db
        self._db.register_model(__USER_MODEL_NAME__, User)
        self._db.register_indexes(__USER_MODEL_NAME__, User, "username")
        self._db.register_indexes(__USER_MODEL_NAME__, User, "email")
        self._db.register_indexes(__USER_MODEL_NAME__, User, "mobile")

        # 初始化管理员用户
        self.ensure_admin_user()

    def get_user(self, user_id: str) -> Optional[User]:
        """通过ID获取用户对象"""
        user = self._db[user_id]
        if not user:
            return None
        return user

    def create_user(self, user: User) -> Result[Tuple[User, Optional[str]]]:
        """创建新用户"""
        check_result = self.existing_index_field(field_path="username", field_value=user.username)
        if not check_result.is_ok():
            return Result.fail(check_result.error)
        
        self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
        return Result.ok(data=user.model_dump(exclude={"password_hash"}), message="用户创建成功")

    def existing_index_field(self, field_path: str, field_value: Any) -> bool:
        """检查字段是否存在"""
        items = self._db.items_with_indexes(__USER_MODEL_NAME__, field_path=field_path, field_value=field_value)
        if items:
            return Result.fail(f"{field_path} 已存在")
        return Result.ok()

    def verify_password(self, username: str, password: str) -> Result[Dict[str, Any]]:
        """验证用户密码"""
        try:
            self._logger.info(f"开始验证用户密码: {username}")

            users = self._db.values_with_indexes(__USER_MODEL_NAME__, field_path="username", field_value=username)
            self._logger.info(f"users: {users}")

            if not users:
                return Result.fail("用户不存在")
            if len(users) > 1:
                self._logger.error(f"用户名不唯一: {username}")
            
            user = users[0]
            self._logger.info(f"用户信息: {user}")

            # 验证密码
            verify_result = user.verify_password(password)
            # 根据 argon2 的安全要求，如果密码需要重新哈希，则需要更新数据库
            if verify_result["rehash"]:
                self._db.put(user.user_id, user)
            
            return Result.ok(data=user.model_dump(exclude={"password_hash"}))
        except Exception as e:
            return Result.fail(f"密码验证失败: {str(e)}")

    def update_user_roles(self, user_id: str, roles: List[str]) -> Result[None]:
        """更新用户角色"""
        try:
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            user.roles = {UserRole(role) for role in roles}
            self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
            return Result.ok(data=user.model_dump(exclude={"password_hash"}))
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
            
            if "username" in kwargs:
                check_result = self.existing_index_field(field_path="username", field_value=kwargs["username"])
                if not check_result.is_ok():
                    return Result.fail(check_result.error)
            
            for key, value in kwargs.items():
                setattr(user, key, value)

            self._db.update_with_indexes(__USER_MODEL_NAME__, user.user_id, user)
            return Result.ok(data=user.model_dump(exclude={"password_hash"}))

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
            if user := self._db[user_id]:
                users.append(user)
        return users
    
    def change_password(self, user_id: str, current_password: str, new_password: str) -> Result[None]:
        """修改用户密码"""
        try:
            user = self.get_user(user_id)
            if not user:
                return Result.fail("用户不存在")

            # 验证旧密码
            if not user.verify_password(current_password):
                return Result.fail("旧密码错误")

            return self.reset_password(user_id, new_password)

        except Exception as e:
            return Result.fail(f"修改用户密码失败: {str(e)}")

    def reset_password(self, user_id: str, new_password: str) -> Result[None]:
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

    def ensure_admin_user(self) -> None:
        """确保管理员用户存在"""
        try:
            admin = self._db.get(__ADMIN_USER_ID__)
            if not admin:
                self._logger.info(f"管理员用户不存在，开始创建")
                self.create_user(User(
                    user_id=__ADMIN_USER_ID__,
                    username=__ADMIN_USERNAME__,
                    password_hash=User.hash_password(__ADMIN_PASSWORD__),
                    roles=[UserRole.ADMIN],
                    require_password_change=False
                ))
                self._logger.debug(f"管理员用户已创建")
            else:
                self._logger.debug(f"管理员用户已存在")
                
        except Exception as e:
            raise
