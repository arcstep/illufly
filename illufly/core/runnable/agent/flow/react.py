from typing import Union, List, Callable

from .....io import EventBlock
from ...template import Template
from ..tools_calling import BaseToolCalling, Plans
from .base import BaseFlowAgent

class ReAct(BaseFlowAgent):
    """
    ReAct 提供了一种更易于人类理解、诊断和控制的决策和推理过程。
    它的典型流程可以用一个有趣的循环来描述：思考（Thought）→ 行动（Action）→ 观察（Observation），简称TAO循环。
    """
    def __init__(self, planner: Callable=None, template: Template=None, solver: Callable=None, handler_tool_call: BaseToolCalling=None, **kwargs):
        self.planner = planner
        self.template = template or Template("FLOW/ReAct")
        self.solver = solver or self.default_solver
        self.handler_tool_call = handler_tool_call or Plans()
        super().__init__(
            self.template,
            self.planner,
            self.solver,
            handler_tool_call=self.handler_tool_call,
            **kwargs
        )

