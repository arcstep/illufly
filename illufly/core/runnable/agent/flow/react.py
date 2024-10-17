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
        planner: BaseAgent,
        tools: List[BaseAgent]=None,
        handler_tool_call: BaseToolCalling=None,
        final_answer_prompt: str=None,
        **kwargs
    ):
        merged_tools = planner.tools + (tools or [])
        self.planner = planner.reset(
            reinit=True,
            memory=PromptTemplate("FLOW/ReAct-Planner"),
            tools=merged_tools
        )
        self.handler_tool_call = handler_tool_call or Plans(tools_to_exec=self.planner.get_tools())
        self.final_answer_prompt = final_answer_prompt or "**最终答案**"

        def should_continue(vars, runs):
            return "END" if runs[0].provider_dict.get("final_answer", None) else runs[0].name

        super().__init__(
            self.planner,
            Selector([self.planner], condition=should_continue),
            **kwargs
        )

        if not self.planner.get_tools():
            raise ValueError("planner 必须提供 tools")

    def begin_call(self):
        super().begin_call()
        if isinstance(self.handler_tool_call, Plans):
            self.handler_tool_call.reset()

    def before_agent_call(self, agent: BaseAgent):
        agent.reset()

    def after_agent_call(self, agent: BaseAgent):
        output = agent.last_output
        self.completed_work.append(output)
        self._last_output = agent.provider_dict["task"]

        # 提取最终答案
        if self.final_answer_prompt in output:
            final_answer_index = output.index(self.final_answer_prompt)
            self.final_answer = output[final_answer_index:].split(self.final_answer_prompt)[-1].strip()

        # 调用工具，并观察工具执行结果
        if self.handler_tool_call and not self.final_answer:
            tools_resp = []
            for block in self.handler_tool_call.handle(agent.last_output):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                    action_result = block.text
                    tools_resp.append(action_result)
                yield block

            if tools_resp:
                action_result = '\n'.join(tools_resp)
                observation = f"\n**观察** 上面的行动结果为:\n{action_result}\n"
                self.completed_work.append(observation)
                yield EventBlock("text", observation)

