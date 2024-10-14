from typing import Union, List, Callable

from .....io import EventBlock
from ...template import Template
from ..tools_calling import BaseToolCalling, Plans
from .base import BaseFlowAgent

class ReWOO(BaseFlowAgent):
    """
    ReWOO 是一种高效的增强语言模型框架，它通过分离 LLM 的推理过程和外部工具调用，并利用可预测推理能力和参数效率，
    实现了更轻量级和可扩展的 ALM 系统。ReWOO 将 ALM 的核心组件分为 Planner、Worker 和 Solver 三个模块，
    Planner 负责制定解决问题的计划，Worker 负责使用外部工具获取证据，Solver 负责根据计划和证据得出最终答案。
    这种方式避免了传统 ALM 中推理和观察的交织，减少了 token 消耗，提高了效率。
    同时，ReWOO 可以通过指令微调和模型专化，将 LLM 的通用推理能力迁移到更小的语言模型中，实现更轻量级的 ALM 系统。
    ReWOO 在多个 NLP 基准数据集上取得了与 ReAct 相当或更好的性能，同时减少了 token 消耗，为构建更高效、可扩展的 ALM 提供了一种新的思路。
    """
    def __init__(self, planner: Callable=None, template: Template=None, solver: Callable=None, handler_tool_call: BaseToolCalling=None, **kwargs):
        self.planner = planner
        self.template = template or Template("FLOW/ReWOO")
        self.solver = solver or self.default_solver
        self.handler_tool_call = handler_tool_call or Plans()
        super().__init__(
            self.template,
            self.planner,
            self.solver,
            handler_tool_call=self.handler_tool_call,
            **kwargs
        )

