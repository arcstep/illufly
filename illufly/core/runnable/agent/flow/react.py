from typing import Union, List, Callable

from .....io import EventBlock
from ...prompt_template import PromptTemplate
from ..tools_calling import BaseToolCalling, SingleAction
from .base import FlowAgent

class ReAct(FlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    def __init__(self, planner: Callable=None, solver: Callable=None, handler_tool_call: BaseToolCalling=None, **kwargs):
        default_handler = SingleAction(tools_to_exec=self.planner.get_tools())
        self.handler_tool_call = handler_tool_call or default_handler

        super().__init__(
            self.planner,
            self.solver,
            handler_tool_call=self.handler_tool_call,
            **kwargs
        )
