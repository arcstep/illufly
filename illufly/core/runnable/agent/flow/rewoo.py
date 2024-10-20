from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from .base import FlowAgent

import json

class ReWOO(FlowAgent):
    """
    ReWOO 是一种高效的增强语言模型框架，它通过分离 LLM 的推理过程和外部工具调用，并利用可预测推理能力和参数效率，
    实现了更轻量级和可扩展的 ALM 系统。ReWOO 将 ALM 的核心组件分为 Planner、Worker 和 Solver 三个模块，
    Planner 负责制定解决问题的计划，Worker 负责使用外部工具获取证据，Solver 负责根据计划和证据得出最终答案。
    这种方式避免了传统 ALM 中推理和观察的交织，减少了 token 消耗，提高了效率。
    同时，ReWOO 可以通过指令微调和模型专化，将 LLM 的通用推理能力迁移到更小的语言模型中，实现更轻量级的 ALM 系统。
    ReWOO 在多个 NLP 基准数据集上取得了与 ReAct 相当或更好的性能，同时减少了 token 消耗，为构建更高效、可扩展的 ALM 提供了一种新的思路。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "planner": "计划器",
            "solver": "求解器",
            "planner_template": "计划器提示语模板, 默认为 PromptTemplate('FLOW/ReWOO/Planner')",
            "solver_template": "求解器提示语模板, 默认为 PromptTemplate('FLOW/ReWOO/Solver')",
            "final_answer_prompt": "最终答案提示词关键字, 默认为 **最终答案**",
            **FlowAgent.available_init_params(),
        }
        
    def __init__(
        self,
        planner: BaseAgent,
        solver: BaseAgent,
        planner_template: PromptTemplate=None,
        solver_template: PromptTemplate=None,
        final_answer_prompt: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(planner, BaseAgent):
            raise ValueError("planner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")
        if planner is solver:
            raise ValueError("planner 和 solver 不能相同")

        planner_template = planner_template or PromptTemplate("FLOW/ReWOO/Planner")
        solver_template = solver_template or PromptTemplate("FLOW/ReWOO/Solver")

        planner.tools_behavior = "parse-execute"
        planner.reset_init_memory(planner_template)
        planner.bind_consumer(planner_template)

        solver.tools_behavior = "nothing"
        solver.reset_init_memory(solver_template)
        solver.bind_consumer(solver_template)

        self.final_answer_prompt = final_answer_prompt or "**最终答案**"
        self.planner = planner
        self.solver = solver

        class Observer(BaseAgent):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.completed_work = []

            @property
            def provider_dict(self):
                return {
                    "completed_work": "\n".join(self.completed_work),
                    **super().provider_dict,
                }

            def call(self, agent: BaseAgent, **kwargs):
                if agent.tools_calling_steps:
                    for step in agent.tools_calling_steps:
                        self.completed_work.append(
                            f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n{step["eid"]} 执行结果: {step["result"]}\n'
                        )
                    self._last_output = self.consumer_dict.get("task", "请开始")

        observer = Observer(name="observer")
        observer.bind_provider(planner)
        observer.bind_consumer(solver)

        super().__init__(
            planner,
            observer,
            solver,
            **filter_kwargs(kwargs, self.available_init_params())
        )
    
    def begin_call(self):
        self.planner.memory.clear()
        self.solver.memory.clear()

    def end_call(self):
        if self.final_answer_prompt in self.last_output:
            final_answer_index = self.last_output.index(self.final_answer_prompt)
            self._last_output = self.last_output[final_answer_index:].split(self.final_answer_prompt)[-1].strip()
