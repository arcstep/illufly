from typing import Union, List, Callable

from .....utils import extract_segments
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..tools_calling import BaseToolCalling, Plans, SubTask
from .base import FlowAgent

class ReAct(FlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    def __init__(
        self,
        planner: Callable,
        tools: List[BaseAgent]=None,
        handler_tool_call: BaseToolCalling=None,
        **kwargs
    ):
        merged_tools = planner.tools + (tools or [])
        planner = planner.__class__(
            name=planner.name,
            memory=PromptTemplate("FLOW/ReAct"),
            tools=merged_tools,
            new_chat=True
        )
        self.handler_tool_call = handler_tool_call or Plans(tools_to_exec=planner.get_tools())

        def should_continue(vars, runs):
            return "END" if runs[0].provider_dict.get("final_answer", None) else planner.name

        super().__init__(
            planner,
            Selector([planner], condition=should_continue),
            **kwargs
        )

        self.completed_work = ""
        self.final_answer = None

    @property
    def provider_dict(self):
        return {
            **super().provider_dict,
            "completed_work": self.completed_work,
            "final_answer": self.final_answer
        }

    def after_agent_call(self, agent: BaseAgent):
        output = agent.last_output
        self.completed_work += f"\n{output}"
        self._last_output = agent.provider_dict["task"]

        # 调用工具，并观察工具执行结果
        if self.handler_tool_call:
            tools_resp = []
            for block in self.handler_tool_call.handle(agent.last_output):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                    action_result = block.text
                    observation = f"\n\n**观察** 上面的行动结果为:\n{action_result}\n" if action_result else "\n"
                    self.completed_work += observation
                    yield EventBlock("text", observation)
                    tools_resp.append(action_result)
                yield block

        # 提取最终答案
        if "**最终答案**" in output:
            final_answer_index = output.index("**最终答案**")
            self.final_answer = output[final_answer_index:].split("**最终答案**")[-1].strip()

        yield EventBlock("info", f"执行完毕。")
