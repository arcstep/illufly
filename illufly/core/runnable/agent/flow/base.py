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
        """
        初始化 FlowAgent

        agents 是一个字典列表，键值是流程中的名称，值是一个 BaseAgent 或 Selector 实例。
        也可以直接传入一个 BaseAgent 列表，由初始化函数自动生成相应的键名。
        """
        raise_invalid_params(kwargs, self.available_init_params())
        super().__init__(**filter_kwargs(kwargs, self.available_init_params()))

        self.max_steps = max_steps or 20

        self.agents = []
        self.agents_index = {}

        for i, agent in enumerate(agents):
            if isinstance(agent, dict):
                node_name = list(agent.keys())[0]
                agent = list(agent.values())[0]
                self.agents.append((node_name, agent))
                self.agents_index[node_name] = (i, agent)
            elif isinstance(agent, (BaseAgent, Selector)):
                if agent.name in self.agents_index:
                    node_name = f"{agent.name}-{len(self.agents_index)}"
                else:
                    node_name = agent.name
                self.agents.append((node_name, agent))
                self.agents_index[node_name] = (i, agent)

        for (name, agent) in self.agents:
            if not isinstance(agent, (BaseAgent, Selector)):
                raise ValueError("only accept BaseAgent or Selector join to Flow")

    def get_agent(self, name):
        return self.agents_index.get(name, (None, None))[2]

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

    def is_end(self, agent):
        if isinstance(agent, str):
            return agent.lower() == "__end__"
        elif isinstance(agent, BaseAgent):
            return agent.name.lower() == "__end__"

        raise ValueError("agent must be a str or BaseAgent")

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """

        (current_node_name, current_agent) = self.agents[0]
        current_index = 0
        current_args = args
        current_kwargs = kwargs
        steps_count = 0

        self.begin_call()

        while(steps_count < self.max_steps):
            # 如果 current_agent 是一个选择器
            selected_agent = current_agent.selected

            # 如果已经到了 __End__  节点，就退出
            if self.is_end(selected_agent):
                break

            # 确保正确获得 agent 和 当前 index
            (current_index, selected_agent) = self.agents_index.get(current_node_name, (None, None))
            if current_index is None:
                break

            # 广播节点信息
            info = self._get_node_info(current_index + 1, current_node_name)
            yield EventBlock("agent", info)

            call_resp = selected_agent.call(*current_args, **current_kwargs)
            if isinstance(call_resp, Generator):
                yield from call_resp

            if selected_agent.last_output:
                # 如果节点已经有了最终的输出，就保存到 FlowAgent 的 last_output 属性中
                self._last_output = selected_agent.last_output

            # 构造下一次调用的参数
            current_args = [selected_agent]

            if (current_index + 1) >= len(self.agents):
                # 如果已经超出最后一个节点，就结束
                break
            else:
                # 否则继续处理下一个节点
                (current_node_name, current_agent) = self.agents[current_index + 1]

            steps_count += 1

        self.end_call()

        yield EventBlock("info", f"执行完毕，所有节点运行 {steps_count} 步")

    def _get_node_info(self, index, node_name):
        return f">>> Node {index}: {node_name}"

