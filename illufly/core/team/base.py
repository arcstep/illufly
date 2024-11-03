from typing import Set, Union
import uuid

from ...config import get_env

class Team:
    """
    实现团队协作，管理多个 BaseAgent 实例，以及他们之间的共享资源。
    """
    def __init__(
        self,
        agents: Set[Union["ChatAgent"]]=None,
        chat_learn_folder: str=None,
        name: str=None,
        description: str=None,
    ):
        self.name = name or str(uuid.uuid4())
        self.description = description or ""
        self.agents = agents if agents else set()
        self.chat_learn_folder = chat_learn_folder or get_env("ILLUFLY_CHAT_LEARN")

    def __repr__(self):
        return f"Team(name={self.name}, agents={self.names}, folder={self.folders})"

    @property
    def names(self):
        return [agent.name for agent in self.agents]

    @property
    def folders(self):
        return [self.chat_learn_folder]

    def hire(self, agent: Union["ChatAgent"]):
        """
        雇佣一个智能体
        """
        agent.team = self
        self.agents.add(agent)

    def fire(self, agent: Union["ChatAgent"]):
        """
        解雇一个智能体
        """
        agent.team = None
        self.agents.discard(agent)
