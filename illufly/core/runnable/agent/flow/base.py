import re

from typing import List, Union
from .....io import EventBlock, NewLineBlock
from .....utils import minify_text
from ...selector import Selector
from ..base import BaseAgent
from ..tools_calling import BaseToolCalling

class FlowAgent(BaseAgent):
    def __init__(self, *agents, handler_tool_call: BaseToolCalling=None, max_steps: int=None, **kwargs):
        super().__init__(**kwargs)

        self.max_steps = max_steps or 20
        self.handler_tool_call = handler_tool_call

        self.agents = agents
        for r in self.agents:
            if not isinstance(r, (BaseAgent, Selector)):
                raise ValueError("only accept BaseAgent or Selector join to Flow")
            self.bind_consumer(r)

    @property
    def provider_dict(self):
        return {
            **super().provider_dict
        }

    def get_agent_by_name(self, name: str):
        """
        构建一个从名字查找 Agent 和 位置的索引
        """
        all = {a.name: (i, a) for i, a in enumerate(self.agents)}
        return all.get(name, None)

    def after_agent_call(self, provider_dict: dict):
        self._last_output = provider_dict["last_output"]

    def after_tool_call(self, tool_resp: str):
        self._last_output = tool_resp

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """
        # kwargs.update({"new_chat": True})

        current_agent = self.agents[0]
        current_index = 0
        current_args = args
        current_kwargs = kwargs
        steps_count = 0
        self._last_output = None

        while(steps_count < self.max_steps):
            # 如果 current_agent 是一个选择器
            selected_agent = current_agent.selected
            if isinstance(selected_agent, str):
                (current_index, selected_agent) = self.get_agent_by_name(selected_agent)

            # 如果已经到了 __End__  节点，就退出            
            if selected_agent.name.lower() == "__end__":
                print("selected_agent", selected_agent)
                break

            # 广播节点信息
            info = self._get_node_info(current_index + 1, selected_agent, steps_count + 1)
            yield EventBlock("agent", info)

            # 绑定并调用 Agent
            self.bind_consumer(selected_agent, dynamic=True)
            yield from selected_agent.call(*current_args, **kwargs)
            yield from self.after_agent_call(selected_agent.provider_dict)

            # 调用工具
            if self.handler_tool_call and isinstance(selected_agent, BaseAgent) and isinstance(selected_agent.last_output, str):
                # 仅根据 ChatAgent 的结果进行工具回调
                tools_resp = []
                for block in self.handler_tool_call.handle(selected_agent.last_output):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        tools_resp.append(block.text)
                    yield block
                yield from self.after_tool_call("\n".join(tools_resp))

            if (current_index + 1) == len(self.agents):
                # 如果已经超出最后一个节点，就结束
                break
            else:
                # 否则继续处理下一个节点
                current_index += 1
                current_agent = self.agents[current_index]

            # 构造下一次调用的参数
            current_args = [self._last_output]
            steps_count += 1

    def _get_node_info(self, index, agent, steps_count):
        return f"STEP {steps_count} >>> Node {index}: {agent.name}"

