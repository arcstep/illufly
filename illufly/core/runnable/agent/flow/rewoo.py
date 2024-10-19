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
            "planner": "计划者",
            "solver": "求解者",
            **FlowAgent.available_init_params(),
        }
        
    def __init__(
        self,
        planner: BaseAgent,
        solver: BaseAgent,
        planner_template: PromptTemplate=None,
        solver_template: PromptTemplate=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(planner, BaseAgent):
            raise ValueError("planner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")

        planner_template = planner_template or PromptTemplate("FLOW/ReWOO/Planner")
        solver_template = solver_template or PromptTemplate("FLOW/ReWOO/Solver")

        planner.tools_behavior = "parse-execute"
        planner.set_init_messages(planner_template)
        planner.bind_consumer(planner_template)

        solver.set_init_messages(solver_template)
        solver.bind_consumer(solver_template)

        class Observer(BaseAgent):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.completed_work = []

                self.bind_provider(planner)
                self.bind_consumer(solver)

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

        super().__init__(
            planner,
            observer,
            solver,
            **filter_kwargs(kwargs, self.available_init_params())
        )
