from typing import Union, List

from ......io import EventBlock
from ....template import Template
from ...base import BaseAgent
from ..base import BaseTeam

class StepByStep(BaseTeam):
    """
    StepByStep 协作规则类似于 ReAct 智能体实践模式，主要通过提示语模板来控制推理过程，具体为：
        - 评估
        - 交办
        - 观察
        …（评估/交办/观察的过程可循环 N 次）
        - 结束
    """
    def __init__(self, leader: BaseAgent, leader_prompt_template: str="", **kwargs):
        self.leader = leader.__class__(
            name=leader.name,
            description=leader.description,
            memory=[Template(kwargs.get("leader_prompt_template", "TEAM/STEP_BY_STEP")), "请开始任务"]
        )

        super().__init__(leader=leader, **kwargs)

    def call(self, prompt: Union[str, List[dict]], **kwargs):
        """
        调用团队协作完成任务。
        """ 
        self._completed_teamwork = []
        self._last_output = None
        max_rounds = 10
        task_index = 0
        for round in range(max_rounds):
            to_continue = False
            yield EventBlock("agent", f"ROUND {round + 1} @{self.leader.name}")
            yield from self.leader.call(prompt, new_chat=True, **kwargs)
            self._last_output = self.leader.last_output
            if not self._completed_teamwork:
                self._completed_teamwork.append(f'[总任务目标] {self.leader.task}')

            self_solve = self.extract_self_solve(self.leader.last_output)
            if self_solve:
                self._completed_teamwork.append(f'[行动] 该子任务自己解决，结果为 {self_solve}')

            tasks = self.extract_task_dispatch(self.leader.last_output)
            for task in tasks:
                task_detail = task["task_detail"]
                member = self.find_member(task["member_name"])
                if member and task_detail:
                    self._completed_teamwork.append(f'[行动] #E{task_index + 1} 子任务交给 @{member.name}, 要求为 {task_detail}')
                    yield EventBlock("agent", f"ROUND {round + 1} @{member.name}")
                    yield from member.call(task_detail, new_chat=True, **kwargs)

                    self._completed_teamwork.append(f'[观察] @{member.name} 已完成 #E{task_index + 1} 子任务，回复内容为 {member.last_output}')
                    to_continue = True

            if not to_continue:
                break

        final_answers = self.extract_answers(self.leader.last_output)
        if final_answers:
            self._completed_teamwork.append(f'[最终答案] \n{final_answers[-1]}')
            self._last_output = final_answers[-1]
            yield EventBlock("final_answer", self._last_output)
        else:
            yield EventBlock("final_answer", "经过多次尝试，没有找到最终答案")