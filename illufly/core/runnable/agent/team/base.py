from typing import Union, List, Dict, Any
from .....io import EventBlock
from ...binding_manager import BindingManager
from ..base import BaseAgent
import json

class Team(BaseAgent, BindingManager):
    """
    智能体团队通过协作完成任务。

    主要的协作模式包括：
        StepByStep - 评估、交办、观察、评估 … 结束
        TaskFlow - 评估、交办、交办 … 结束
        PlanOnce - 评估、计划、交办、总结
        PlanDynamic - 评估、计划、交办、观察、计划、交办、观察 … 结束
        Discuss - 评估、主张、争论、主张 、争论 … 结束
        IdeaStorm - 评估、脑暴 … 总结    
    """
    def __init__(self, leader: BaseAgent, *members: BaseAgent, **kwargs):
        super().__init__(**kwargs)
        BindingManager.__init__(self, **kwargs)

        self.leader = leader
        self.members = list(members)
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
        members_desc = [{m.name: m.description} for m in self.members]

        return {
            **super().exported_vars,
            "members": json.dumps(members_desc, ensure_ascii=False),
            "completed_teamwork": self.completed_teamwork
        }

    def call(self, prompt: Union[str, List[dict]], **kwargs):
        """
        调用团队协作完成任务。
        """
        self._completed_teamwork = []
        max_rounds = 3
        for round in range(max_rounds):
            to_continue = False
            yield EventBlock("info", f"ROUND {round + 1}")
            yield from self.leader.call(prompt, new_chat=True, **kwargs)
            tasks = self.extract_task_dispatch(self.leader.last_output)
            for task in tasks:
                member = self.find_member(task["member_name"])
                if member:
                    self._completed_teamwork.append(f'交办：一个任务交办给 {task["member_name"]}, 任务描述: {task["description"]}')
                    yield from member.call(task["description"], **kwargs)
                    self._completed_teamwork.append(f'观察：由 {task["member_name"]} 回复， {member.last_output}')
                    to_continue = True
                else:
                    raise ValueError(f"member {task} not found")
            final_answer = self.extract_final_answer(self.leader.last_output)
            if final_answer:
                yield EventBlock("final_answer", final_answer)
                return final_answer
            if not to_continue:
                break

        yield EventBlock("final_answer", "经过多次尝试，没有找到最终答案")

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