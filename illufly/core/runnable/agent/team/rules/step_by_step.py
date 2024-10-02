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
        max_rounds = 3
        for round in range(max_rounds):
            to_continue = False
            yield EventBlock("agent", f"ROUND {round + 1} @{self.leader.name}")
            yield from self.leader.call(prompt, new_chat=True, **kwargs)

            tasks = self.extract_task_dispatch(self.leader.last_output)
            for task in tasks:
                member = self.find_member(task["member_name"])
                if member:
                    self._completed_teamwork.append(f'[交办] 一个任务交办给 @{task["member_name"]}, 详细任务为 {task["description"]}')
                    yield EventBlock("agent", f"ROUND {round + 1} @{member.name}")
                    yield from member.call(task["description"], new_chat=True, **kwargs)

                    self._completed_teamwork.append(f'[观察] 由 @{task["member_name"]} 回复， {member.last_output}')
                    to_continue = True
                else:
                    raise ValueError(f"member {task} not found")

            final_answer = self.extract_final_answer(self.leader.last_output)
            if final_answer:
                self._completed_teamwork.append(f'[最终答案] \n{final_answer}')
                self._last_output = final_answer
                yield EventBlock("final_answer", final_answer)
                return final_answer

            if not to_continue:
                break

        yield EventBlock("final_answer", "经过多次尝试，没有找到最终答案")