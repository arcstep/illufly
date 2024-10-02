from typing import Union, List, Dict, Any
from ...binding_manager import BindingManager
from ..base import BaseAgent
import json

class BaseTeam(BaseAgent, BindingManager):
    """
    智能体团队通过协作完成任务。
    """
    def __init__(self, leader: BaseAgent, members: List[BaseAgent]=None, **kwargs):
        super().__init__(**kwargs)
        BindingManager.__init__(self, **kwargs)

        self.members = members or []
        self._completed_teamwork = []

        if not isinstance(leader, BaseAgent):
            raise ValueError("leader must be a BaseAgent instance")

        if len(members) == 0:
            raise ValueError("at least one member must be provided")

        if not all(isinstance(m, BaseAgent) for m in members):
            raise ValueError("members must be a list of BaseAgent instances")

        # 从领导角色和成员角色绑定到 Team
        self.leader.bind((self, {}))
        for m in self.members:
            m.bind((self, {}))

    @property
    def completed_teamwork(self):
        return self._completed_teamwork
    
    @property
    def exported_vars(self):
        members_desc = []
        names = set([self.leader.name])
        for index, m in enumerate(self.members):
            if m.name not in names:
                _name = m.name
                names.add(_name)
            else:
                _name = f"{m.name}_{index}"
                m.name = _name
            members_desc.append({"member_name": m.name, "description": m.description})

        return {
            **super().exported_vars,
            "members": json.dumps(members_desc, ensure_ascii=False),
            "completed_teamwork": self.completed_teamwork
        }

    def find_member(self, name: str) -> BaseAgent:
        for m in self.members:
            if m.name == name:
                return m
        return None

    def extract_final_answer(self, text: str) -> str:
        start_marker = "<final_answer>"
        end_marker = "</final_answer>"
        start = text.find(start_marker)
        while start != -1:
            end = text.find(end_marker, start)
            if end != -1:
                final_answer = text[start + len(start_marker):end]
                return final_answer
            else:
                break
        return None

    def extract_task_dispatch(self, text: str) -> str:
        tasks = []
        start_marker = "<task_dispatch>"
        end_marker = "</task_dispatch>"
        start = text.find(start_marker)
        while start != -1:
            end = text.find(end_marker, start)
            if end != -1:
                task_dispatch = text[start + len(start_marker):end]
                try:
                    task = json.loads(task_dispatch)
                    tasks.append(task)
                except json.JSONDecodeError:
                    pass
                start = text.find(start_marker, end)
            else:
                break
        return tasks