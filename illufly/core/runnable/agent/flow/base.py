import re

from typing import List, Union, Generator, AsyncGenerator
from .....io import EventBlock, NewLineBlock
from .....utils import minify_text
from ...selector import Selector
from ..base import BaseAgent

class FlowAgent(BaseAgent):
    def __init__(self, *agents, max_steps: int=None, **kwargs):
        super().__init__(**kwargs)

        self.max_steps = max_steps or 20

        self.agents = agents
        for r in self.agents:
            if not isinstance(r, (BaseAgent, Selector)):
                raise ValueError("only accept BaseAgent or Selector join to Flow")
            self.bind_consumer(r)

        self.completed_work = []
        self.final_answer = None

    @property
    def provider_dict(self):
        return {
            **super().provider_dict,
            "completed_work": "\n".join(self.completed_work),
            "final_answer": self.final_answer
        }

    def reset(self):
        super().reset()

        self.completed_work.clear()
        self.final_answer = None
        for agent in self.agents:
            agent.reset()

    def get_agent_by_name(self, name: str):
        """
        构建一个从名字查找 Agent 和 位置的索引
        """
        all = {a.name: (i, a) for i, a in enumerate(self.agents)}
        return all.get(name, None)

    def begin_call(self):
        pass

    def end_call(self):
        pass

    def before_agent_call(self, agent: BaseAgent):
        pass

    def after_agent_call(self, agent: BaseAgent):
        self._last_output = agent.provider_dict["last_output"]

        if not self.completed_work:
            if agent.provider_dict.get("task", None):
                self.completed_work.append("**任务**\n" + agent.provider_dict["task"])
        self.completed_work.append(f'@{agent.name} :\n{self._last_output}')

    def call(self, *args, **kwargs):
        """
        执行智能体管道。
        """

        current_agent = self.agents[0]
        current_index = 0
        current_args = args
        current_kwargs = kwargs
        steps_count = 0
        self.reset()

        self.begin_call()
        while(steps_count < self.max_steps):
            # 如果 current_agent 是一个选择器
            selected_agent = current_agent.selected
            if isinstance(selected_agent, str):
                (current_index, selected_agent) = self.get_agent_by_name(selected_agent)

            self.before_agent_call(selected_agent)

            # 如果已经到了 __End__  节点，就退出            
            if selected_agent.name.lower() == "__end__":
                break

            # 广播节点信息
            info = self._get_node_info(current_index + 1, selected_agent, steps_count + 1)
            yield EventBlock("agent", info)

            # 绑定并调用 Agent
            self.bind_consumer(selected_agent, dynamic=True)

            call_resp = selected_agent.call(*current_args, **current_kwargs)
            if isinstance(call_resp, Generator):
                yield from call_resp

            after_call_resp = self.after_agent_call(selected_agent)
            if isinstance(after_call_resp, Generator):
                yield from after_call_resp

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

        self.end_call()

    def _get_node_info(self, index, agent, steps_count):
        return f"STEP {steps_count} >>> Node {index}: {agent.name}"

