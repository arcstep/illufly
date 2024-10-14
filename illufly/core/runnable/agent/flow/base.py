import re

from typing import List, Union
from .....io import EventBlock
from .....utils import minify_text
from ..base import BaseAgent
from ...template import Template
from ..tools_calling import BaseToolCalling

def default_solver(steps):
    return "\n".join([step.get('result') for step in steps if step.get('result')])

class FlowAgent(BaseAgent):
    def __init__(self, *runnables, handler_tool_call: BaseToolCalling=None, solver: BaseAgent=None, **kwargs):
        super().__init__(**kwargs)

        self.handler_tool_call = handler_tool_call

        self.runnables = runnables
        for r in self.runnables:
            self.bind_consumer(r)

        _solver = solver or default_solver
        self.solver = _solver if isinstance(_solver, BaseAgent) else BaseAgent(_solver)
        self.bind_consumer(self.solver)

        self.steps = []

    @property
    def provider_dict(self):
        return {
            **super().provider_dict,
            "steps": self.steps
        }

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """
        kwargs.update({"new_chat": True})
        self.steps = []
        prev_runnable = None
        for index, run in enumerate(self.runnables):
            info = self._get_node_info(index + 1, run.selected)
            yield EventBlock("agent", info)
            if index == 0:
                current_args = args
                current_kwargs = kwargs
            else:
                self._last_output = prev_runnable.last_output
                if self.handler_tool_call and isinstance(prev_runnable, BaseAgent) and isinstance(self._last_output, str):
                    # 仅根据 ChatAgent 的结果进行工具回调
                    tool_calls = self.handler_tool_call.extract_tools_call(self._last_output)
                    if tool_calls:
                        for index, tool_call in enumerate(tool_calls):
                            for block in self.handler_tool_call.handle_tools_call(tool_call, kwargs):
                                yield block
                        self._last_output = self.solver.call(self.steps)
                current_args = [self._last_output]

            yield from run.selected.call(*current_args, **kwargs)
            prev_runnable = run.selected

            if isinstance(run, Template):
                self._last_output = run
            else:
                self._last_output = run.last_output

    def _get_node_info(self, index, run):
        if isinstance(run, BaseAgent):
            if run.memory:
                info = f">>> Node {index}: {minify_text(run.memory[0].get('content'), 30, 30, 10)}"
            else:
                info = f">>> Node {index}: {run.__class__.__name__}"
        else:
            info = f">>> Node {index}: {run.__class__.__name__}"
        return info

