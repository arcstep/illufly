from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
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
    @classmethod
    def available_init_params(cls):
        return {
            "planner": "计划者",
            "tools": "工具列表",
            "handler_tool_call": "工具调用处理器",
            "final_answer_prompt": "最终答案提示词",
            **FlowAgent.available_init_params(),
        }

    def __init__(
        self,
        planner: BaseAgent,
        tools: List[BaseAgent]=None,
        handler_tool_call: BaseToolCalling=None,
        final_answer_prompt: str=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        merged_tools = planner.tools + (tools or [])
        self.planner = planner.reset(
            reinit=True,
            memory=PromptTemplate("FLOW/ReAct/Planner"),
            tools=merged_tools
        )
        self.handler_tool_call = handler_tool_call or Plans(tools_to_exec=self.planner.get_tools())
        self.final_answer_prompt = final_answer_prompt or "**最终答案**"

        def should_continue(vars, runs):
            return "END" if runs[0].provider_dict.get("final_answer", None) else runs[0].name

        super().__init__(
            self.planner,
            Selector([self.planner], condition=should_continue),
            **filter_kwargs(kwargs, self.available_init_params())
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
        """
        在调用完 agent 之后，进行一些处理。
        1. 将 agent 的输出添加到 completed_work 中，作为 T-A-O 循环的 T 部份
        2. 将 agent 的输出设置为 _last_output
        3. 根据 final_answer_prompt 提取 final_answer
        4. 调用工具，并观察工具执行结果，并补充到 completed_work 中，作为 T-A-O 循环的 O 部份
        """
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

