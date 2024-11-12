from typing import Union, List, Callable

from .....utils import filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..chat import ChatAgent
from .base import FlowAgent

class ReAct(FlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "planner": "用于推理的ChatAgent, 你应当在其中指定可用的工具",
            "planner_template": "用于生成计划的PromptTemplate, 默认为 PromptTemplate('FLOW/ReAct/Planner')",
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
        # if not planner.tools:
        #     raise ValueError("planner 必须包含可用的工具")

        planner_template = planner_template or PromptTemplate("FLOW/ReAct/Planner")
        self.planner_template = planner_template

        # 设置 planner 的 tools_behavior 为 "parse-execute"，执行后就停止，等待 T-A-O 循环
        planner.tools_behavior = "parse-execute"
        planner.reset_init_memory(planner_template)
        self.planner = planner
        self.completed_work = []

        def observe_func(agent: BaseAgent):
            output = agent.last_output

            if output:
                self.completed_work.append(output)
            else:
                if not planner.final_answer:
                    yield self.create_event_block("warn", f"观察结果中没有 final_answer，可能导致无法结束")

            if agent.tools_calling_steps:
                all_results = "\n".join([step["result"] for step in agent.tools_calling_steps])
                observation = f'\n**观察**\n上面的行动结果为:\n{all_results}\n'
                yield self.create_event_block("text", observation)

                self.completed_work.append(observation)
                planner_template.bind_provider({
                    "completed_work": "\n".join(self.completed_work)
                })

            yield self.create_event_block("final_text", self.task)

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
