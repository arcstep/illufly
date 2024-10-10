from typing import List, Union, Optional, Callable
from .....io import EventBlock
from ...base import Runnable
from ..base import BaseAgent
import inspect

class RouterAgent(BaseAgent):
    """
    路由选择 Runnable 对象的智能体，并将任务分发给被选择对象执行。

    可以根据模型，以及配置模型所需的工具集、资源、数据、handlers等不同参数，构建为不同的智能体对象。
    """
    def __init__(
        self,
        condition: Callable,
        runnables: List[Runnable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.condition = condition
        self.runnables = runnables if isinstance(runnables, list) else [runnables]

        if runnables and not all(isinstance(router, Runnable) for router in self.runnables):
            raise ValueError("runnables must be a list of BaseAgent")
        
        if not isinstance(condition, Callable):
            raise ValueError("condition must be a Callable")
        
        # 使用 inspect 模块获取函数签名
        signature = inspect.signature(self.condition)
        if len(signature.parameters) == 0:
            raise ValueError("condition must have at least one parameter")

        self.bind_runnables()

    def bind_runnables(self):
        for a in self.runnables:
            self.bind_consumer(a)

    @property
    def selected(self):
        return self.call(only_select=True)

    def call(self, *args, only_select=False, **kwargs) -> List[dict]:
        selected = self.condition(self.runnables, self.consumer_dict)
        if isinstance(selected, Runnable):
            return selected if only_select else selected(*args, **kwargs)
        elif isinstance(selected, str):
            for run in self.runnables:
                if selected.lower() in run.name.lower():
                    return run if only_select else run(*args, **kwargs)

            runnable_names = [r.name for r in self.runnables]
            raise ValueError(f"router {selected} not found in {runnable_names}")

        raise ValueError("selected runnable must be a str(runnable's name) or Runnable object", selected)
