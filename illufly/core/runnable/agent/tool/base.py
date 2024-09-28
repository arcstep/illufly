from typing import Callable, Generator

from .. import BaseAgent
from .....io import TextBlock

class ToolAgent(BaseAgent):
    def __init__(self, func: Callable, **kwargs):
        super().__init__(func=func, **kwargs)

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<Tool {self.name}: {self.description}>"

    def call(self, *args, **kwargs):
        resp = self.func(*args, **kwargs)
        if isinstance(resp, Generator):
            yield from resp
        else:
            yield TextBlock("chunk", resp)
