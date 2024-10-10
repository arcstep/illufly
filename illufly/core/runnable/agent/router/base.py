from typing import List, Union, Optional, Callable
from .....io import EventBlock
from ...base import Runnable
from ..base import BaseAgent
import inspect

class RouterAgent(BaseAgent):
    """
    智能体路由器。
    智能体可以根据模型，以及配置模型所需的工具集、资源、数据、handlers等不同参数，构建为不同的智能体对象。

    根据条件选择一个智能体执行任务。
    condition 必须是 Callable 类型，即函数或者具有 __call__ 方法的对象。
    """
    def __init__(
        self,
        condition: callable,
        agents: List[BaseAgent] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.condition = condition
        self.agents = agents if isinstance(agents, list) else [agents]

        if agents and not all(isinstance(router, BaseAgent) for router in self.agents):
            raise ValueError("agents must be a list of BaseAgent")
        
        if not isinstance(condition, Callable):
            raise ValueError("condition must be a Callable")
        
        # 使用 inspect 模块获取函数签名
        signature = inspect.signature(self.condition)
        if len(signature.parameters) == 0:
            raise ValueError("condition must have at least one parameter")

    def call(self, prompt: Union[str, List[dict]], **kwargs) -> List[dict]:
        agent_names = [a.name for a in self.agents]
        selected_agent_name = self.condition(prompt, agent_names, **kwargs)
        for router in self.agents:
            if selected_agent_name.lower() in router.name.lower():
                return router(prompt, **kwargs)
        raise ValueError(f"router {selected_agent_name} not found in {agent_names}")

