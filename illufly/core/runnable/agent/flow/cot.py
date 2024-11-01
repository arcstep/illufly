from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

class CoT(FlowAgent):
    """
    CoT 是 ReAct 的简化版，提供了一种没有工具的反思过程，有利于单步思考时避免不必要的工具回调。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "planner": "用于推理的ChatAgent, 你应当在其中指定可用的工具",
            "planner_template": "用于生成计划的PromptTemplate, 默认为 PromptTemplate('FLOW/CoT/Planner')",
            **FlowAgent.allowed_params(),
        }

    def __init__(
        self,
        planner: BaseAgent,
        planner_template: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())

        if not isinstance(planner, ChatAgent):
            raise ValueError("planner 必须是 ChatAgent 的子类")

        planner_template = planner_template or PromptTemplate("FLOW/CoT/Planner")
        self.planner_template = planner_template

        planner.reset_init_memory(planner_template)
        self.planner = planner
        self.completed_work = []

        def observe_func(agent: BaseAgent):
            output = agent.last_output

            if output:
                self.completed_work.append(output)
            else:
                yield EventBlock("warn", f"{final_answer_prompt}\n没有可用的输出")

            if agent.last_output:
                observation = f'\n**观察**\n上面的行动结果为:\n{agent.last_output}\n'

                self.completed_work.append(observation)
                planner_template.bind_provider({
                    "completed_work": "\n".join(self.completed_work)
                })

            yield EventBlock("final_text", self.task)

        def should_continue(vars, runs):
            if planner.final_answer:
                return "__END__"
            else:
                planner.clear()
                return "planner"

        super().__init__(
            {"planner": planner},
            {"observer": observe_func},
            Selector(condition=should_continue, name="should_continue"),
            **filter_kwargs(kwargs, self.allowed_params())
        )
    
    def begin_call(self, args):
        self.planner.clear()
        self.completed_work.clear()
        self.planner_template.bind_provider({"completed_work": ""})

        return super().begin_call(args)

    def end_call(self):
        self._last_output = self.planner.final_answer
