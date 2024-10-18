from typing import Union, List, Callable

from .....utils import extract_segments, filter_kwargs, raise_invalid_params
from .....io import EventBlock
from ...selector import Selector
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
# from ..tools_calling import BaseToolCalling, Plans
from .base import FlowAgent

class ReWOO(FlowAgent):
    """
    ReWOO 是一种高效的增强语言模型框架，它通过分离 LLM 的推理过程和外部工具调用，并利用可预测推理能力和参数效率，
    实现了更轻量级和可扩展的 ALM 系统。ReWOO 将 ALM 的核心组件分为 Planner、Worker 和 Solver 三个模块，
    Planner 负责制定解决问题的计划，Worker 负责使用外部工具获取证据，Solver 负责根据计划和证据得出最终答案。
    这种方式避免了传统 ALM 中推理和观察的交织，减少了 token 消耗，提高了效率。
    同时，ReWOO 可以通过指令微调和模型专化，将 LLM 的通用推理能力迁移到更小的语言模型中，实现更轻量级的 ALM 系统。
    ReWOO 在多个 NLP 基准数据集上取得了与 ReAct 相当或更好的性能，同时减少了 token 消耗，为构建更高效、可扩展的 ALM 提供了一种新的思路。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "planner": "计划者",
            "solver": "求解者",
            "tools": "工具列表",
            "handler_tool_call": "工具调用处理器",
            **FlowAgent.available_init_params(),
        }
        
    def __init__(
        self,
        planner: BaseAgent=None,
        solver: BaseAgent=None,
        tools: List[BaseAgent]=None,
        handler_tool_call=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())

        merged_tools = planner.tools + (tools or [])

        self.planner = planner.reset(
            reinit=True,
            memory=PromptTemplate("FLOW/ReWOO/Planner"),
            tools=merged_tools
        )

        self.solver = solver.reset(
            reinit=True,
            memory=PromptTemplate("FLOW/ReWOO/Solver")
        )

        self.handler_tool_call = handler_tool_call or Plans(tools_to_exec=self.planner.get_tools())

        super().__init__(
            self.planner,
            **filter_kwargs(kwargs, self.available_init_params())
        )

        if not self.planner.get_tools():
            raise ValueError("planner 必须提供 tools")

    def begin_call(self):
        super().begin_call()
        if isinstance(self.handler_tool_call, Plans):
            self.handler_tool_call.reset()

    def after_agent_call(self, agent: BaseAgent):
        """
        在调用完 agent 之后，进行一些处理。
        1. 执行 handler_tool_call.handle(agent.last_output)
        2. 将 handler_tool_call.completed_work 和 提取到 completed_work
        3. 将 task 提交给 solver 合成最后输出
        4. 将 solver 的输出设置为 _last_output 并作为 final_answer 返回
        """
        output = agent.last_output
        self._last_output = agent.provider_dict["task"]

        # 调用工具，并观察工具执行结果
        if self.handler_tool_call:
            for block in self.handler_tool_call.handle(agent.last_output):
                yield block

        # 提取最终答案
        self.solver.reset()
        self.solver.bind_provider(
            binding_map={
                "completed_work": self.handler_tool_call.completed_work
            },
            dynamic=True
        )
        yield from self.solver.call(self.agents[0].provider_dict["task"])

        self.final_answer = self.solver.last_output
        self._last_output = self.final_answer

        yield EventBlock("text", f"\n**最终答案**\n{self.final_answer}")
