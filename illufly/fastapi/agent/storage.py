from typing import Dict, Any
from ..common.storage import StorageProtocol
from .models import AgentInfo

class AgentStorage(StorageProtocol[Dict[str, AgentInfo]]):
    """代理存储实现"""
    def __init__(self, data_dir: str, base_path: str):
        """
        Args:
            data_dir: 存储目录
            base_path: 用于加载向量数据库的基础路径
        """
        super().__init__(data_dir)
        self.base_path = base_path

    def _serialize(self, agents: Dict[str, AgentInfo]) -> Dict[str, Any]:
        """序列化代理信息"""
        return {
            name: agent_info.to_dict()
            for name, agent_info in agents.items()
        }

    def _deserialize(self, data: Dict[str, Any], owner: str) -> Dict[str, AgentInfo]:
        """反序列化代理信息
        Args:
            data: 序列化的代理数据
            owner: 数据所有者（用户名）
        """
        return {
            name: AgentInfo.from_dict(
                agent_data,
                username=owner,  # 使用 owner 作为 username
                base_path=self.base_path
            )
            for name, agent_data in data.items()
        } 