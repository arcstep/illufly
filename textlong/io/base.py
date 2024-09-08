from abc import ABC, abstractmethod
from typing import Callable

class BaseLog(ABC):
    @abstractmethod
    def __call__(self, func: Callable, *args, **kwargs):
        pass

    def end(self):
        return None

