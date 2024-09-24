from typing import Callable

from .. import BaseAgent

class ToolAgent(BaseAgent):
    def __init__(self, func: Callable, **kwargs):
        super().__init__(func=func, **kwargs)
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<Tool {self.name}: {self.description}>"

    def call(self, *args, **kwargs):
        yield from self.func(*args, **kwargs)
