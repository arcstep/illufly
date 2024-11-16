from typing import Set, Union
import uuid
import re

from ....io import log, EventBlock
from ....config import get_env
from ..base import Runnable

class Team(Runnable):
    """
    管理多个 ChatAgent 实例，以及他们之间的共享资源、事件收集。
    """
    def __init__(
        self,
        agents: Set[Union["ChatAgent"]]=None,
        default_agent: Union["ChatAgent"]=None,
        chunk_types: list=None,
        other_types: list=None,
        **kwargs
    ):
        super().__init__(
            **kwargs
        )

        self.agents = agents if agents else set()
        self.agents_thread_ids = {}
        self.default_agent = default_agent or next(iter(self.agents), None)

    def __repr__(self):
        return f"Team(name={self.name}, agents={self.names})"

    @property
    def names(self):
        return [agent.name for agent in self.agents]

    def call(self, prompt: str, **kwargs):
        """
        根据 prompt 中包含的 @agent_name 名称调用团队成员，如果未指定就调用默认成员。
        """
        names = self.fetch_agent_names(prompt)
        for name in names:
            prompt = re.sub(rf"(^|\s)@{name}\s", " ", prompt)
        prompt = prompt.strip()
        for agent in self.get_agents(names):
            yield from agent.call(prompt, **kwargs)

    def fetch_agent_names(self, prompt: str):
        """
        返回agent名称列表，如果列表为空就返回self.agents中的第一个
        """
        agent_names = re.findall(r"(?:^|\s)@(\w+)(?=\s)", prompt)
        if agent_names:
            return agent_names
        else:
            return [next(iter(self.agents)).name] if self.agents else []

    def get_agents(self, names: str):
        """
        根据名称返回智能体
        """
        return [agent for agent in self.agents if agent.name in names]

    def hire(self, *agents: Union["ChatAgent"]):
        """
        雇佣一个智能体。
        如果名字相同会保留已有实例，不会重复创建。
        """
        for agent in agents:
            agent.team = self
            self.agents.add(agent)

    def fire(self, *agents: Union["ChatAgent"]):
        """
        解雇一个智能体。
        """
        for agent in agents:
            agent.team = None
            self.agents.discard(agent)
