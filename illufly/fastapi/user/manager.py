from typing import Dict, Optional
from pathlib import Path
import json
import threading
from .context import UserContext
from ..agent.models import AgentInfo
from ..agent.factory import AgentFactory

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
        if not self.data_dir.exists():
            return

        for user_dir in self.data_dir.iterdir():
            if user_dir.is_dir():
                username = user_dir.name
                agents_file = user_dir / "agents.json"
                
                if agents_file.exists():
                    with open(agents_file, 'r') as f:
                        agents_data = json.load(f)
                    
                    context = UserContext(username)
                    for agent_name, agent_data in agents_data.items():
                        agent_info = AgentInfo.from_dict(agent_data)
                        context.add_agent(agent_name, agent_info)
                    
                    self._contexts[username] = context