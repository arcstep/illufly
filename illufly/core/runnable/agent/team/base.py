from typing import Union, List, Dict, Any
from ...binding_manager import BindingManager
from ..base import BaseAgent
from .....utils import extract_segments
import json

class BaseTeam(BaseAgent):
    """
    智能体团队通过协作完成任务。
    """
    def __init__(self, leader: BaseAgent, members: List[BaseAgent]=None, **kwargs):
        super().__init__(**kwargs)

        self.members = members or []
        self._completed_teamwork = []

        if not isinstance(leader, BaseAgent):
            raise ValueError("leader must be a BaseAgent instance")

        if len(members) == 0:
            raise ValueError("at least one member must be provided")

        if not all(isinstance(m, BaseAgent) for m in members):
            raise ValueError("members must be a list of BaseAgent instances")

        # 从领导角色和成员角色绑定到 Team
        self.leader.bind_providers((self, {}))
        for m in self.members:
            m.bind_providers((self, {}))

    @property
    def completed_teamwork(self):
        return self._completed_teamwork
    
    @property
    def provider_dict(self):
        members_desc = []
        names = set([self.leader.name])
        for index, m in enumerate(self.members):
            if m.name not in names:
                _name = m.name
                names.add(_name)
            else:
                _name = f"{m.name}_{index}"
                m.name = _name
            members_desc.append({"成员名字": m.name, "擅长能力": m.description})

        return {
            **super().provider_dict,
            "members": json.dumps(members_desc, ensure_ascii=False),
            "completed_teamwork": "\n".join(self.completed_teamwork)
        }

    def find_member(self, name: str) -> BaseAgent:
        for m in self.members:
            if m.name == name:
                return m
        return None

    def extract_answer(self, text: str) -> str:
        return extract_segments(text, "<final_answer>", "</final_answer>")

    def extract_self_solve(self, text: str) -> str:
        return extract_segments(text, "<self_solve>", "</self_solve>")

    def extract_task_dispatch(self, text: str) -> str:
        tasks = extract_segments(text, "<sub_task>", "</sub_task>")
        for task in tasks:
            try:
                task = json.loads(task)
                tasks.append(task)
            except json.JSONDecodeError:
                pass
        return tasks
