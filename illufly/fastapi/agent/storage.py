from typing import Dict, Any
from ..common.storage import BaseStorage
from .models import AgentInfo

class AgentStorage(BaseStorage[Dict[str, AgentInfo]]):
    """代理存储实现"""
    def _serialize(self, agents: Dict[str, AgentInfo]) -> Dict[str, Any]:
        """序列化代理信息
        Args:
            agents: 代理信息字典 {agent_name: agent_info}
        """
        return {
            name: agent_info.to_dict()
            for name, agent_info in agents.items()
        }

    def _deserialize(self, data: Dict[str, Any]) -> Dict[str, AgentInfo]:
        """反序列化代理信息
        Args:
            data: 序列化的代理数据
        """
        return {
            name: AgentInfo.from_dict(agent_data)
            for name, agent_data in data.items()
        } 