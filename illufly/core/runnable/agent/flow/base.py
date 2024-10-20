import re

from typing import List, Union, Generator, AsyncGenerator
from .....io import EventBlock, NewLineBlock
from .....utils import minify_text, filter_kwargs, raise_invalid_params
from ...selector import Selector
from ..base import BaseAgent

class FlowAgent(BaseAgent):
    @classmethod
    def available_init_params(cls):
        return {
            "max_steps": "最大步骤数",
            **BaseAgent.available_init_params(),
        }

    def __init__(self, *agents, max_steps: int=None, **kwargs):
        raise_invalid_params(kwargs, self.available_init_params())
        super().__init__(**filter_kwargs(kwargs, self.available_init_params()))

        self.max_steps = max_steps or 20

        self.agents = agents
        for r in self.agents:
            if not isinstance(r, (BaseAgent, Selector)):
                raise ValueError("only accept BaseAgent or Selector join to Flow")

    def begin_call(self):
        """
        开始执行的回调方法。
        """
        pass

    def end_call(self):
        """
        结束执行的回调方法。
        """
        pass

    def get_agent_by_name(self, name: str):
        """
        构建一个从名字查找 Agent 和 位置的索引
        """
        all = {a.name: (i, a) for i, a in enumerate(self.agents)}
        return all.get(name, None)

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """

        current_agent = self.agents[0]
        current_index = 0
        current_args = args
        current_kwargs = kwargs
        steps_count = 0

        self.begin_call()

        while(steps_count < self.max_steps):
            # 如果 current_agent 是一个选择器
            selected_agent = current_agent.selected
            agent_name = selected_agent if isinstance(selected_agent, str) else selected_agent.name

            # 如果已经到了 __End__  节点，就退出            
            if agent_name.lower() == "__end__":
                break

            # 确保正确获得 agent 和 当前 index
            (current_index, selected_agent) = self.get_agent_by_name(agent_name)

            # 广播节点信息
            info = self._get_node_info(current_index + 1, selected_agent)
            yield EventBlock("agent", info)

            call_resp = selected_agent.call(*current_args, **current_kwargs)
            if isinstance(call_resp, Generator):
                yield from call_resp

            if selected_agent.last_output:
                # 如果节点已经有了最终的输出，就保存到 FlowAgent 的 last_output 属性中
                self._last_output = selected_agent.last_output

            if (current_index + 1) == len(self.agents):
                # 如果已经超出最后一个节点，就结束
                break
            else:
                # 否则继续处理下一个节点
                current_index += 1
                current_agent = self.agents[current_index]

            # 构造下一次调用的参数
            current_args = [selected_agent]
            steps_count += 1

        self.end_call()

        yield EventBlock("info", f"执行完毕，所有节点运行 {steps_count} 步")

    def _get_node_info(self, index, agent):
        return f">>> Node {index}: {agent.name}"

