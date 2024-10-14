import re

from typing import List, Union
from .....io import EventBlock
from .....utils import minify_text
from ..base import BaseAgent
from ..tools_calling import BaseToolCalling

def default_solver(steps):
    return "\n".join([step.get('result') for step in steps if step.get('result')])

class FlowAgent(BaseAgent):
    def __init__(self, *agents, handler_tool_call: BaseToolCalling=None, solver: BaseAgent=None, **kwargs):
        super().__init__(**kwargs)

        self.handler_tool_call = handler_tool_call

        self.agents = agents
        for r in self.agents:
            if not isinstance(r, BaseAgent):
                raise ValueError("only accept BaseAgent join to Flow")
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
        prev_agent = None
        for index, agent in enumerate(self.agents):
            info = self._get_node_info(index + 1, agent.selected)
            yield EventBlock("agent", info)
            if index == 0:
                current_args = args
                current_kwargs = kwargs
            else:
                if self.handler_tool_call and isinstance(prev_agent, BaseAgent) and isinstance(self._last_output, str):
                    # 仅根据 ChatAgent 的结果进行工具回调
                    tool_calls = self.handler_tool_call.extract_tools_call(self._last_output)
                    if tool_calls:
                        for index, tool_call in enumerate(tool_calls):
                            for block in self.handler_tool_call.handle_tools_call(tool_call, kwargs):
                                yield block
                        self._last_output = self.solver.call(self.steps)
                current_args = [self._last_output]

            prev_agent = agent.selected

            yield from agent.selected.call(*current_args, **kwargs)
            self._last_output = agent.last_output

    def _get_node_info(self, index, agent):
        return f">>> Node {index}: {agent.__class__.__name__}"

