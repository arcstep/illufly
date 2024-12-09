from typing import Dict, Optional, List, Any
from datetime import datetime
from ..agent.models import AgentInfo

class UserContext:
    def __init__(self, username: str):
        self.username = username
        self.agents: Dict[str, AgentInfo] = {}
        self.last_active = datetime.now()
        self._is_loaded = False

    def add_agent(self, name: str, agent_info: AgentInfo) -> bool:
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

    def get_agent_info(self, name: str) -> Optional[AgentInfo]:
        return self.agents.get(name)

    def list_agents(self) -> List[AgentInfo]:
        return list(self.agents.values())