from typing import Callable, Dict, Any
import uuid
import inspect

from .base import Runnable

class Tool(Runnable):
    def __init__(self, func: Callable=None, **kwargs):
        super().__init__(func=func, **kwargs)

    def call(self, *args, **kwargs):
        for block in self.func(*args, **kwargs):
            yield block