from typing import Dict, Optional, List, Any
from datetime import datetime
from .models import User

class UserContext:
    def __init__(self, username: str):
        self.username = username
        self.user: Optional[User] = None
        self.agents: Dict[str, Any] = {}
        self.last_active = datetime.now()
        self._is_loaded = False

    def update_user_info(self, **kwargs) -> bool:
        """更新用户信息"""
        if not self.user:
            return False

        for key, value in kwargs.items():
            if hasattr(self.user, key):
                setattr(self.user, key, value)
        return True

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        if not self.user:
            return None
        return self.user.to_dict()

    def add_agent(self, name: str, agent_info: Any) -> bool:
        if name in self.agents:
            return False
        self.agents[name] = agent_info
        return True

    def remove_agent(self, name: str) -> bool:
        if name not in self.agents:
            return False
        agent_info = self.agents.pop(name)
        if hasattr(agent_info.instance, 'cleanup'):
            agent_info.instance.cleanup()
        return True

    def get_agent(self, name: str) -> Optional[Any]:
        agent_info = self.agents.get(name)
        if agent_info:
            agent_info.last_used = datetime.now()
            return agent_info.instance
        return None

    def get_agent_info(self, name: str) -> Optional[Any]:
        return self.agents.get(name)

    def list_agents(self) -> List[Any]:
        return list(self.agents.values())

    def update_password(self, old_password: str, new_password: str) -> bool:
        """更新用户密码"""
        if not self.user:
            return False
        
        if not self.user.verify_password(old_password):
            return False
        
        self.user.password_hash = User.hash_password(new_password)
        return True