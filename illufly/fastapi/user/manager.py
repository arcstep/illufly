from typing import Dict, Optional, Any, List, Tuple
from pathlib import Path
import json
import threading
from datetime import datetime
from .models import User, UserRole
from .context import UserContext
import secrets
import string

class UserManager:
    def __init__(self, data_dir: str = "data/users"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._contexts: Dict[str, UserContext] = {}
        self._lock = threading.Lock()
        self._load_users_from_disk()

    def create_agent(self, username: str, agent_type: str, agent_name: str, 
                    vectordbs: list, **kwargs) -> bool:
        context = self._contexts.get(username)
        if not context:
            context = UserContext(username)
            self._contexts[username] = context

        base_path = f"./__data__/{username}"
        try:
            agent_info = AgentFactory.create_agent(
                agent_type=agent_type,
                agent_name=agent_name,
                base_path=base_path,
                vectordbs=vectordbs,
                **kwargs
            )
        except ValueError as e:
            return False

        success = context.add_agent(agent_name, agent_info)
        if success:
            self._save_user_agents(username)
        return success

    def get_user_context(self, username: str) -> Optional[UserContext]:
        return self._contexts.get(username)

    def get_agent(self, username: str, agent_name: str) -> Optional[Any]:
        context = self._contexts.get(username)
        if context:
            return context.get_agent(agent_name)
        return None

    def _save_user_agents(self, username: str):
        user_dir = self.data_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)
        
        context = self._contexts[username]
        agents_data = {
            name: agent_info.to_dict()
            for name, agent_info in context.agents.items()
        }
        
        with open(user_dir / "agents.json", 'w') as f:
            json.dump(agents_data, f, indent=2)

    def _load_users_from_disk(self):
        """从磁盘加载所有用户信息"""
        if not self.data_dir.exists():
            return

        for user_dir in self.data_dir.iterdir():
            if user_dir.is_dir():
                username = user_dir.name
                context = UserContext(username)
                
                # 加载用户基本信息
                user_file = user_dir / "user.json"
                if user_file.exists():
                    with open(user_file, 'r') as f:
                        user_data = json.load(f)
                    context.user = User.from_dict(user_data)
                
                # 加载用户代理信息
                agents_file = user_dir / "agents.json"
                if agents_file.exists():
                    with open(agents_file, 'r') as f:
                        agents_data = json.load(f)
                    
                    for agent_name, agent_data in agents_data.items():
                        agent_info = AgentInfo.from_dict(agent_data)
                        context.add_agent(agent_name, agent_info)
                
                # 只有当用户信息存在时才添加到上下文中
                if context.user:
                    self._contexts[username] = context

    @staticmethod
    def generate_random_password(length: int = 12) -> str:
        """生成随机密码
        Args:
            length: 密码长度
        Returns:
            str: 随机密码
        """
        # 包含大小写字母、数字和特殊字符
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        # 确保密码包含至少一个数字和一个特殊字符
        password = ''.join(secrets.choice(alphabet) for _ in range(length-2))
        password += secrets.choice(string.digits)
        password += secrets.choice("!@#$%^&*")
        # 打乱密码顺序
        password_list = list(password)
        secrets.SystemRandom().shuffle(password_list)
        return ''.join(password_list)

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
        with self._lock:
            if username in self._contexts:
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
            context = UserContext(username)
            context.user = user
            self._contexts[username] = context
            self._save_user_to_disk(username)
            
            return True, generated_password

    def verify_user_password(self, username: str, password: str) -> Tuple[bool, bool]:
        """验证用户密码
        Returns:
            Tuple[bool, bool]: (密码是否正确, 是否需要修改密码)
        """
        context = self._contexts.get(username)
        if not context or not context.user:
            return False, False
        
        password_correct = context.user.verify_password(password)
        
        # 检查是否需要修改密码（包括强制修改和密码过期）
        need_change = (
            context.user.require_password_change or 
            context.user.is_password_expired()
        )
        
        return password_correct, need_change

    def update_user_roles(self, username: str, roles: List[str]) -> bool:
        """更新用户角色"""
        with self._lock:
            context = self._contexts.get(username)
            if not context:
                return False

            context.user.roles = set(roles)
            self._save_user_to_disk(username)
            return True

    def list_users(self) -> List[Dict[str, Any]]:
        """列出所有用户（不包含敏感信息）"""
        with self._lock:
            return [context.user.to_dict(include_sensitive=False) 
                    for context in self._contexts.values()]

    def update_user_context(self, username: str, **kwargs) -> bool:
        """更新用户上下文信息"""
        with self._lock:
            context = self._contexts.get(username)
            if not context:
                return False

            for key, value in kwargs.items():
                setattr(context.user, key, value)
            self._save_user_to_disk(username)
            return True

    def _save_user_to_disk(self, username: str):
        """保存用户信息到磁盘"""
        user_dir = self.data_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)
        
        context = self._contexts[username]
        # 保存到磁盘时包含密码哈希
        user_data = context.user.to_dict(include_sensitive=True)
        
        with open(user_dir / "user.json", 'w') as f:
            json.dump(user_data, f, indent=2)

    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """修改用户密码"""
        with self._lock:
            context = self._contexts.get(username)
            if not context or not context.user:
                return False
            
            # 验证旧密码
            if not context.user.verify_password(old_password):
                return False
            
            # 更新密码哈希和相关信息
            context.user.password_hash = User.hash_password(new_password)
            context.user.last_password_change = datetime.now()
            context.user.require_password_change = False
            
            # 保存到磁盘
            self._save_user_to_disk(username)
            return True

    def reset_password(self, username: str, new_password: str, admin_required: bool = True) -> bool:
        """重置用户密码（管理员功能）
        Args:
            username: 用户名
            new_password: 新密码
            admin_required: 是否需要管理员权限
        Returns:
            bool: 是否重置成功
        """
        with self._lock:
            context = self._contexts.get(username)
            if not context or not context.user:
                return False
            
            # 更新密码哈希
            context.user.password_hash = User.hash_password(new_password)
            
            # 保存到磁盘
            self._save_user_to_disk(username)
            return True