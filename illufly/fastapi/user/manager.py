from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
import secrets
import string
from pathlib import Path
from ...config import get_env
from ..common import ConfigStoreProtocol, FileConfigStore
from ..auth import AuthManager
from .models import User, UserRole
import uuid

__USERS_PATH__ = get_env("ILLUFLY_FASTAPI_USERS_PATH")

class UserManager:
    def __init__(self, auth_manager: AuthManager, storage: Optional[ConfigStoreProtocol[User]] = None):
        """初始化用户管理器
        Args:
            auth_manager: 认证管理器
            storage: 存储实现，如果为None则使用默认的文件存储
        """
        self.auth_manager = auth_manager
        if storage is None:
            storage = FileConfigStore[User](
                data_dir=Path(__USERS_PATH__),
                filename="profile.json",
                serializer=lambda user: user.to_dict(include_sensitive=True),
                deserializer=User.from_dict,
                use_id_subdirs=True
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
        """创建新用户"""
        username = username or email

        # 检查用户名或邮箱是否已存在
        exists, field, existing_user = self._storage.exists({
            "username": username,
            "email": email,
        })
        
        if exists:
            return {
                "success": False,
                "generated_password": None,
                "user": None,
                "error": f"{field} '{getattr(existing_user, field)}' already exists"
            }

        # 生成随机密码（如果没有提供）
        generated_password = None
        if not password:
            generated_password = self.generate_random_password()
            password = generated_password

        # 对密码进行哈希处理
        hash_result = self.auth_manager.hash_password(password)
        if not hash_result["success"]:
            return {
                "success": False,
                "generated_password": None,
                "user": None,
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
        self._storage.set(user.user_id, user, owner_id=user.user_id)
        
        return {
            "success": True,
            "generated_password": generated_password,
            "user": user,
            "error": None
        }

    def verify_user_password(self, username: str, password: str) -> Dict[str, Any]:
        """验证用户密码"""
        user = self.get_user_by_username(username)
        print(">>> user", user)
        if not user:
            return {
                "success": False, 
                "require_password_change": False, 
                "user": None,
                "error": "User not found"
            }
        
        # 验证密码
        verify_result = self.auth_manager.verify_password(password, user.password_hash)
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

    def update_user_roles(self, user_id: str, roles: List[str]) -> Dict[str, Any]:
        """更新用户角色"""
        user = self._storage.get(user_id, owner_id=user_id)
        if not user:
            return {
                "success": False,
                "error": "User not found"
            }

        try:
            user_roles = {UserRole(role) for role in roles}
            user.roles = user_roles
            self._storage.set(user_id, user, owner_id=user_id)
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
            if user := self._storage.get(user_id, owner_id=user_id):
                users.append(user.to_dict(include_sensitive=False))
        return users

    def update_user(self, user_id: str, **kwargs) -> Dict[str, Any]:
        """更新用户信息"""
        try:    
            user = self._storage.get(user_id, owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self._storage.set(user_id, user, owner_id=user_id)
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
            user = self._storage.get(user_id, owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            # 验证旧密码
            verify_result = self.auth_manager.verify_password(old_password, user.password_hash)
            if not verify_result["success"]:
                return {
                    "success": False,
                    "error": verify_result["error"]
                }

            # 对新密码进行哈希处理
            hash_result = self.auth_manager.hash_password(new_password)
            if not hash_result["success"]:
                return {
                    "success": False,
                    "error": hash_result["error"]
                }

            user.password_hash = hash_result["hash"]
            user.last_password_change = datetime.now()
            user.require_password_change = False
            
            self._storage.set(user_id, user, owner_id=user_id)
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
            user = self._storage.get(user_id, owner_id=user_id)
            if not user:
                return {
                    "success": False,
                    "error": "User not found"
                }

            # 对新密码进行哈希处理
            hash_result = self.auth_manager.hash_password(new_password)
            if not hash_result["success"]:
                return {
                    "success": False,
                    "error": hash_result["error"]
                }
        
            user.password_hash = hash_result["hash"]
            user.last_password_change = datetime.now()
            user.require_password_change = True
            
            self._storage.set(user_id, user, owner_id=user_id)
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
            if not self._storage.delete(user_id, owner_id=user_id):
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
        print(f">>> 正在查找用户名: {username}")
        print(f">>> 数据目录: {__USERS_PATH__}")
        
        try:
            # 遍历所有用户ID
            owners = self._storage.list_owners()
            print(f">>> 所有用户ID: {owners}")
            
            for user_id in owners:
                try:
                    # 使用user_id作为存储键和owner_id
                    user = self._storage.get(user_id, owner_id=user_id)
                    print(f">>> 检查用户ID {user_id} 的数据: {user}")
                    if user and user.username == username:  # 匹配username
                        print(f">>> 找到匹配用户: {user}")
                        return user
                except Exception as e:
                    print(f">>> 获取用户 {user_id} 时出错: {e}")
                    continue
                
            print(">>> 未找到匹配用户")
            return None
            
        except Exception as e:
            print(f">>> 查找用户时发生错误: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """通过邮箱获取用户"""
        for user_id in self._storage.list_owners():
            if user := self._storage.get(user_id, owner_id=user_id):
                if user.email == email:
                    return user
        return None

    def verify_invite_code(self, invite_code: str) -> bool:
        """验证邀请码
        Args:
            invite_code: 待验证的邀请码
        Returns:
            bool: 邀请码是否有效
        """
        # TODO: 实现邀请码验证逻辑
        return True

    def ensure_admin_user(self) -> None:
        """确保管理员用户存在"""
        try:
            print(">>> 开始检查管理员用户")
            admin = self.get_user_by_username("admin")
            
            if not admin:
                print(">>> 创建管理员用户")
                # 使用固定的user_id作为存储键
                admin_id = "admin"
                result = self.create_user(
                    username="admin",  # 显示名称
                    password="admin",
                    email="admin@illufly.com",
                    user_id=admin_id,  # 存储键
                    roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.USER, UserRole.GUEST],
                    require_password_change=False
                )
                
                if result["success"]:
                    admin = result["user"]
                    print(">>> 成功创建管理员用户")
                else:
                    print(f">>> 创建管理员用户失败: {result.get('error')}")
                    return
            else:
                print(">>> 管理员用户已存在")
            
            if admin:
                self._admin_ids.add(admin.user_id)  # 使用user_id而不是username
                print(">>> 管理员用户已就绪")
                
        except Exception as e:
            print(f">>> 确保管理员用户存在时发生错误: {e}")
            raise

