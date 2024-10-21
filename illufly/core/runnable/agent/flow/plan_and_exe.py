from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ...selector import Selector, End
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
            "worker": "执行者",
            "replanner": "重新计划者",
            "planner_template": "计划者模板",
            "worker_template": "执行者模板",
            "replanner_template": "重新计划者模板",
            "final_answer_prompt": "最终答案提示词",
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
        final_answer_prompt: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(planner, BaseAgent) or not isinstance(worker, BaseAgent) or not isinstance(replanner, BaseAgent):
            raise ValueError("planner, worker, replanner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")
        if planner is worker or planner is replanner or worker is replanner:
            raise ValueError("planner, worker, replanner 不能相同")

        self.final_answer_prompt = final_answer_prompt or "**最终答案**"

        planner_template = planner_template or PromptTemplate("FLOW/PlanAndExe/Planner")
        self.planner_template = planner_template

        replanner_template = replanner_template or PromptTemplate("FLOW/PlanAndExe/RePlanner")
        self.replanner_template = replanner_template

        worker_template = worker_template or PromptTemplate("FLOW/PlanAndExe/Worker")
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

        self.done = []
        self.todo = []

        def observe_worker_for_replanner(agent: BaseAgent):
            replanner.memory.clear()
            self.todo.clear()

            if agent.tools_calling_steps:
                for step in agent.tools_calling_steps:
                    item = f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n'
                    item = f'{item}{step["eid"]} 执行结果: {step["result"]}\n'
                    self.done.append(item)

            binding_map = {
                "plan_todo": "\n".join(self.todo),
                "plan_done": "\n".join(self.done)
            }

            self.replanner_template.bind_provider(binding_map)

            yield EventBlock("final_text", planner.provider_dict['task'])

        def observe_plan_for_worker(agent: BaseAgent):
            worker.memory.clear()
            if agent.tools_calling_steps:
                for step in agent.tools_calling_steps:
                    item = f'Step{step["index"]}: {step["description"]}\n{step["eid"]} = {step["name"]}[{step["arguments"]}]\n'
                    self.todo.append(item)

            binding_map = {
                "plan_todo": "\n".join(self.todo)
            }

            self.worker_template.bind_provider(binding_map)

            yield EventBlock("final_text", "请开始\n")

        def should_continue(vars, runs):
            if (self.final_answer_prompt in self.replanner.last_output):
                return "__END__"
            else:
                self.replanner.memory.clear()
                return "observe_plan_for_worker"

        super().__init__(
            {"planner": planner},
            {"observe_plan_for_worker": observe_plan_for_worker},
            {"worker": worker},
            {"observe_worker_for_replanner": observe_worker_for_replanner},
            {"replanner": replanner},
            Selector([], condition=should_continue, name="should_continue"),
            **filter_kwargs(kwargs, self.available_init_params())
        )

    def begin_call(self):
        self.planner.memory.clear()
        self.done.clear()
        self.todo.clear()

    def end_call(self):
        if self.final_answer_prompt in self.last_output:
            final_answer_index = self.last_output.index(self.final_answer_prompt)
            self._last_output = self.last_output[final_answer_index:].split(self.final_answer_prompt)[-1].strip()
