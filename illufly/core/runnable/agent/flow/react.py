from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from .base import FlowAgent

class ReAct(FlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "planner": "用于推理的ChatAgent, 你应当在其中指定可用的工具",
            "planner_template": "用于生成计划的PromptTemplate, 默认为 PromptTemplate('FLOW/ReAct/Planner')",
            "final_answer_prompt": "最终答案提示词关键字, 默认为 **最终答案**",
            **FlowAgent.available_init_params(),
        }

    def __init__(
        self,
        planner: BaseAgent,
        planner_template: str=None,
        final_answer_prompt: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        if not isinstance(planner, BaseAgent):
            raise ValueError("planner 必须是 ChatAgent 的子类")
        if not planner.tools:
            raise ValueError("planner 必须包含可用的工具")

        final_answer_prompt = final_answer_prompt or "**最终答案**"
        self.final_answer_prompt = final_answer_prompt

        planner_template = planner_template or PromptTemplate("FLOW/ReAct/Planner")
        self.planner_template = planner_template

        # 设置 planner 的 tools_behavior 为 "parse-execute"，执行后就停止，等待 T-A-O 循环
        planner.tools_behavior = "parse-execute"
        planner.reset_init_memory(planner_template)
        self.planner = planner

        def observe_func(agent: BaseAgent):
            output = agent.last_output
            completed_work = []

            if output:
                completed_work.append(output)
            else:
                yield EventBlock("warn", f"{final_answer_prompt}\n没有可用的输出")

            if agent.tools_calling_steps:
                all_results = "\n".join([step["result"] for step in agent.tools_calling_steps])
                observation = f'\n**观察**\n上面的行动结果为:\n{all_results}\n'
                yield EventBlock("text", observation)

                completed_work.append(observation)
                planner_template.bind_provider({
                    "completed_work": "\n".join(completed_work)
                })

            yield EventBlock("final_text", agent.provider_dict['task'])

        def should_continue(vars, runs):
            if final_answer_prompt in planner.last_output:
                return "__END__"
            else:
                planner.memory.clear()
                return "planner"

        super().__init__(
            {"planner": planner},
            {"observer": observe_func},
            Selector([], condition=should_continue, name="should_continue"),
            **filter_kwargs(kwargs, self.available_init_params())
        )
    
    def begin_call(self):
        self.planner.memory.clear()

    def end_call(self):
        if self.final_answer_prompt in self.last_output:
            final_answer_index = self.last_output.index(self.final_answer_prompt)
            self._last_output = self.last_output[final_answer_index:].split(self.final_answer_prompt)[-1].strip()
