from typing import List, Union, Generator, AsyncGenerator
from ..base import BaseAgent
from ...selector import Selector

class RouterAgent(BaseAgent, Selector):
    """
    路由选择 Runnable 对象的智能体，并将任务分发给被选择对象执行。

    可以根据模型，以及配置模型所需的工具集、资源、数据、handlers等不同参数，构建为不同的智能体对象。
    """
    def __init__(
        self,
        agents: List[BaseAgent] = None,
        condition: Union[BaseAgent, str] = None,
        **kwargs
    ):
        BaseAgent.__init__(self, func=None, async_func=None, **kwargs)
        Selector.__init__(self, runnables=agents, condition=condition, **kwargs)

    def call(self, *args, **kwargs):
        return Selector.call(self, *args, **kwargs)

    async def async_call(self, *args, **kwargs):
        resp = Selector.async_call(self, *args, **kwargs)
        if isinstance(resp, Generator):
            for block in resp:
                yield block
        elif isinstance(resp, AsyncGenerator):
            async for block in resp:
                yield block
        else:
            yield resp