from typing import Union, List, Callable

from .....utils import extract_segments
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..tools_calling import BaseToolCalling, SubTask
from .base import FlowAgent

def should_continue(vars, runs):
    if "<final_answer>" in runs[0].last_output:
        return "END"
    else:
        return runs[0]

class ReAct(FlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    def __init__(self, planner: Callable=None, tools: List[BaseAgent]=None, handler_tool_call: BaseToolCalling=None, **kwargs):
        merged_tools = planner.tools + (tools or [])
        planner = planner.__class__(
            memory=PromptTemplate("FLOW/ReAct"),
            tools=merged_tools,
            new_chat=True
        )
        default_handler = SubTask(tools_to_exec=planner.get_tools())
        super().__init__(
            planner,
            Selector([planner], condition=should_continue),
            handler_tool_call=handler_tool_call or default_handler,
            **kwargs
        )

        self.completed_work = ""

    @property
    def provider_dict(self):
        return {
            **super().provider_dict,
            "completed_work": self.completed_work
        }

    def after_call(self, provider_dict: dict):
        output = provider_dict["last_output"]
        self._last_output = provider_dict["task"]

        final_answer = extract_segments(output, "<final_answer>", "</final_answer>")
        if final_answer:
            yield EventBlock("text", f"最终答案为: {final_answer}")

        self.completed_work += f"\n{output}"
        yield EventBlock("info", f"执行完毕。")

    def after_tool_call(self, output: str):
        observation = f"\n\n**观察** 上面的行动结果为:\n{output}\n" if output else "\n"
        self.completed_work += observation
        yield EventBlock("text", observation)
