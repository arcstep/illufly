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

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        if not self.user:
            return None
        return self.user.to_dict()

    def add_agent(self, name: str, agent_info: Any) -> bool:
        """添加代理，确保代理名称唯一"""
        if not self._is_loaded:
            return False
        if name in self.agents:
            return False
        self.agents[name] = agent_info
        self.last_active = datetime.now()
        return True

    def remove_agent(self, name: str) -> bool:
        """移除代理"""
        if not self._is_loaded or name not in self.agents:
            return False
        agent_info = self.agents.pop(name)
        if hasattr(agent_info.instance, 'cleanup'):
            agent_info.instance.cleanup()
        self.last_active = datetime.now()
        return True

    def get_agent(self, name: str) -> Optional[Any]:
        """获取代理实例，并更新最后使用时间"""
        if not self._is_loaded:
            return None
        agent_info = self.agents.get(name)
        if agent_info:
            agent_info.last_used = datetime.now()
            self.last_active = datetime.now()
            return agent_info.instance
        return None

    def get_agent_info(self, name: str) -> Optional[Any]:
        """获取代理信息"""
        if not self._is_loaded:
            return None
        return self.agents.get(name)

    def list_agents(self) -> List[str]:
        """列出所有代理名称"""
        if not self._is_loaded:
            return []
        return list(self.agents.keys())

    def load(self) -> bool:
        """标记上下文已加载"""
        self._is_loaded = True
        return True

    def is_loaded(self) -> bool:
        """检查上下文是否已加载"""
        return self._is_loaded

    def update_agent_config(self, name: str, config_updates: Dict[str, Any]) -> bool:
        """更新代理配置
        Args:
            name: 代理名称
            config_updates: 需要更新的配置项
        Returns:
            bool: 是否更新成功
        """
        if not self._is_loaded:
            return False
        
        agent_info = self.agents.get(name)
        if not agent_info:
            return False
        
        # 更新配置
        if hasattr(agent_info, 'config'):
            agent_info.config.update(config_updates)
        else:
            agent_info.config = config_updates
        
        # 如果代理实例支持重新配置，则调用相应方法
        if hasattr(agent_info.instance, 'reconfigure'):
            try:
                agent_info.instance.reconfigure(config_updates)
            except Exception:
                return False
            
        self.last_active = datetime.now()
        return True