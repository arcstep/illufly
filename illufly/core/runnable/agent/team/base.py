from ..base import BaseAgent

class BaseTeam(BaseAgent):
    """
    团队
    """
    def __init__(self, leader: BaseAgent, *members: BaseAgent, **kwargs):
        super().__init__(**kwargs)
        self.leader = leader
        self.members = members

    def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)
    
    @property
    def runnables(self):
        return [self.leader, *self.members]
