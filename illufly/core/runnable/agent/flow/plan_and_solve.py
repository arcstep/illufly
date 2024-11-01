from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ...selector import Selector, End
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

import json

class PlanAndSolve(FlowAgent):
    """
    PlanAndSolve 类似于 ReAct, 一边制定总体计划一边执行。
    这既可以通过一步步思考获得稳定推理, 又可以在每次制定更有利于实现总体目标的计划。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "planner": "计划者",
            "worker": "执行者",
            "replanner": "重新计划者",
            "planner_template": "计划者模板",
            "worker_template": "执行者模板",
            "replanner_template": "重新计划者模板",
            **FlowAgent.allowed_params(),
        }
        
    def __init__(
        self,
        planner: ChatAgent,
        worker: ChatAgent,
        replanner: ChatAgent,
        planner_template: PromptTemplate=None,
        worker_template: PromptTemplate=None,
        replanner_template: PromptTemplate=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())

        if not isinstance(planner, ChatAgent) or not isinstance(worker, ChatAgent) or not isinstance(replanner, ChatAgent):
            raise ValueError("planner, worker, replanner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")
        if planner is worker or planner is replanner or worker is replanner:
            raise ValueError("planner, worker, replanner 不能相同")

        planner_template = planner_template or PromptTemplate("FLOW/PlanAndSolve/Planner")
        self.planner_template = planner_template

        replanner_template = replanner_template or PromptTemplate("FLOW/PlanAndSolve/RePlanner")
        self.replanner_template = replanner_template

        worker_template = worker_template or PromptTemplate("FLOW/PlanAndSolve/Worker")
        self.worker_template = worker_template

        planner.tools_behavior = "parse"
        planner.reset_init_memory(planner_template)
        self.planner = planner

        worker.tools_behavior = "parse-execute"
        worker.reset_init_memory(worker_template)
        self.worker = worker

        replanner.tools_behavior = "parse"
        replanner.reset_init_memory(replanner_template)
        self.replanner = replanner

        self.completed_work = []
        self.todo = []

        def observe_worker_for_replanner(agent: BaseAgent):
            replanner.memory.clear()
            self.todo.clear()

            if agent.tools_calling_steps:
                for step in agent.tools_calling_steps:
                    item = f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n'
                    item = f'{item}{step["eid"]} 执行结果: {step["result"]}\n'
                    self.completed_work.append(item)

            self.replanner_template.bind_provider({
                "plan_todo": "\n".join(self.todo),
                "plan_done": "\n".join(self.completed_work)
            })

            yield EventBlock("final_text", self.task)

        def observe_plan_for_worker(agent: BaseAgent):
            worker.memory.clear()
            if agent.tools_calling_steps:
                for step in agent.tools_calling_steps:
                    item = f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n'
                    self.todo.append(item)

            self.worker_template.bind_provider( {
                "plan_todo": "\n".join(self.todo)
            })

            yield EventBlock("final_text", "请开始\n")

        def should_continue(vars, runs):
            if self.replanner.final_answer:
                return "__END__"
            else:
                self.replanner.clear()
                return "observe_plan_for_worker"

        super().__init__(
            {"planner": planner},
            {"observe_plan_for_worker": observe_plan_for_worker},
            {"worker": worker},
            {"observe_worker_for_replanner": observe_worker_for_replanner},
            {"replanner": replanner},
            Selector(condition=should_continue, name="should_continue"),
            **filter_kwargs(kwargs, self.allowed_params())
        )

    def begin_call(self, args):
        self.planner.clear()
        self.replanner.clear()
        self.worker.clear()
        self.completed_work.clear()
        self.todo.clear()

        return super().begin_call(args)

    def end_call(self):
        self._last_output = self.replanner.final_answer
