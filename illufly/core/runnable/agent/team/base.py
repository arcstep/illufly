from typing import Set

from ..base import BaseAgent

class TeamAgent(BaseAgent):
    """
    实现团队协作，管理多个 BaseAgent 实例，以及他们之间的共享资源。
    """
    def __init__(self, agents: Set[BaseAgent]=None, **kwargs):
        super().__init__(**kwargs)
        self.agents = agents if agents else set()

    def hire(self, agent: BaseAgent):
        """
        雇佣一个智能体
        """
        self.agents.add(agent)

    def fire(self, agent: BaseAgent):
        """
        解雇一个智能体
        """
        self.agents.discard(agent)
