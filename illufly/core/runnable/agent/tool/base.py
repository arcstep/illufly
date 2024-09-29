import inspect
from typing import Callable, Generator, Dict, Any

from .. import BaseAgent
from .....io import EventBlock

class ToolAgent(BaseAgent):
    def __init__(self, func: Callable, **kwargs):
        if not isinstance(func, Callable):
            raise ValueError("func must be a callable")

        super().__init__(func=func, **kwargs)
        self.name = kwargs.get("name", func.__name__ if func else self.__class__.__name__)
        self.description = kwargs.get("description", func.__doc__ if func and func.__doc__ else "")

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<Tool {self.name}: {self.description}>"

    def call(self, *args, **kwargs):
        resp = self.func(*args, **kwargs)
        if isinstance(resp, Generator):
            yield from resp
        else:
            yield EventBlock("chunk", resp)
