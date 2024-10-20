from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from .base import FlowAgent

import json

class PlanAndExe(FlowAgent):
    """
    PlanAndExe 类似于 ReAct, 一边制定总体计划一边执行。
    这既可以通过一步步思考获得稳定推理, 又可以在每次制定更有利于实现总体目标的计划。
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
        worker: BaseAgent,
        replanner: BaseAgent,
        planner_template: PromptTemplate=None,
        worker_template: PromptTemplate=None,
        replanner_template: PromptTemplate=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(planner, BaseAgent) or not isinstance(worker, BaseAgent) or not isinstance(replanner, BaseAgent):
            raise ValueError("planner, worker, replanner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")
        if planner is worker or planner is replanner or worker is replanner:
            raise ValueError("planner, worker, replanner 不能相同")

        planner_template = planner_template or PromptTemplate("FLOW/PlanAndExe/Planner")
        replanner_template = replanner_template or PromptTemplate("FLOW/PlanAndExe/RePlanner")
        worker_template = worker_template or PromptTemplate("FLOW/PlanAndExe/Worker")

        planner.tools_behavior = "parse"
        planner.set_init_messages(planner_template)
        planner.bind_consumer(planner_template)

        worker.tools_behavior = "parse-execute"
        worker.set_init_messages(worker_template)
        worker.bind_consumer(worker_template)

        replanner.tools_behavior = "parse"
        replanner.set_init_messages(replanner_template)
        replanner.bind_consumer(replanner_template)

        def should_continue(vars, runs):
            if (final_answer_prompt in planner.last_output) or observer.final_answer:
                return "END"
            else:
                replanner.memory.clear()
                return worker

        observer = Observer(name="observer")

        super().__init__(
            planner,
            worker,
            replanner,
            Selector([], condition=should_continue, name="should_replan"),
            **filter_kwargs(kwargs, self.available_init_params())
        )
