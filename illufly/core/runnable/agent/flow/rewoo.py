from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ...selector import End
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

import json

class ReWOO(FlowAgent):
    """
    ReWOO 在 ReAct 基础上, 一次性生成所有需要的计划, 但取消观察环节, 从而大大减少与LLM的对话次数。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "planner": "计划器，用于生成完成任务所有需要的整体计划",
            "solver": "求解器，根据计划和各步骤执行结果汇总后得出最终答案",
            "planner_template": "计划器提示语模板, 默认为 PromptTemplate('FLOW/ReWOO/Planner')",
            "solver_template": "求解器提示语模板, 默认为 PromptTemplate('FLOW/ReWOO/Solver')",
            **FlowAgent.allowed_params(),
        }
        
    def __init__(
        self,
        planner: BaseAgent,
        solver: BaseAgent,
        planner_template: PromptTemplate=None,
        solver_template: PromptTemplate=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())

        if not isinstance(planner, ChatAgent):
            raise ValueError("planner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")
        if solver is planner:
            raise ValueError("planner 和 solver 不能相同")

        planner_template = planner_template or PromptTemplate("FLOW/ReWOO/Planner")
        self.planner_template = planner_template

        solver_template = solver_template or PromptTemplate("FLOW/ReWOO/Solver")
        self.solver_template = solver_template

        self.planner = planner
        self.solver = solver
        self.completed_work = []

        def observe_func(agent: BaseAgent):
            if agent.tools_calling_steps:
                for step in agent.tools_calling_steps:
                    self.completed_work.append(
                        f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n{step["eid"]} 执行结果: {step["result"]}\n'
                    )
                self.solver_template.bind_provider({
                    "completed_work": "\n".join(self.completed_work)
                })

                return self.task

        super().__init__(
            planner,
            observe_func,
            solver,
            End(),
            **filter_kwargs(kwargs, self.allowed_params())
        )
    
    def begin_call(self, args):
        self.planner.tools_behavior = "parse-execute"
        self.planner.reset_init_memory(self.planner_template)
        self.planner.clear()

        self.solver.tools_behavior = "nothing"
        self.solver.reset_init_memory(self.solver_template)
        self.solver.clear()

        self.solver_template.bind_provider({
            "completed_work": ""
        })

        return super().begin_call(args)

    def end_call(self):
        self._last_output = self.solver.final_answer
