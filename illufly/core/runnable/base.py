import asyncio
import inspect

from typing import Union, List, Dict, Any, Callable
from abc import ABC, abstractmethod
from functools import partial

from .tool_ability import ToolAbility
from .executor_manager import ExecutorManager
from ...io import log

class Runnable(ABC, ToolAbility, ExecutorManager):
    """
    实现基本可运行类，定义了可运行的基本接口。
    只要继承该类，就可以作为智能体的工具使用。
    """

    def __init__(
        self,
        # 线程组
        threads_group: str=None,
        # 是否自动停止
        continue_running: bool=True,
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
        """
        self.continue_running = continue_running
        self._output = None

        ExecutorManager.__init__(self, threads_group)
        ToolAbility.__init__(self, **kwargs)

    def __call__(self, *args, verbose:bool=False, handler:Callable=None, **kwargs):
        handler = handler or log
        return handler(self, *args, verbose=verbose, **kwargs)

    @property
    def output(self):
        return self._output

    @property
    def is_running(self):
        return self.continue_running

    def start(self):
        self.continue_running = True

    def stop(self):
        self.continue_running = False

    @abstractmethod
    def call(self, *args, **kwargs):
        """
        这是同步调用的主入口，默认必须实现该方法。
        """
        raise NotImplementedError("子类必须实现 call 方法")

    async def async_call(self, *args, **kwargs):
        """
        默认的异步调用，通过多线程实现。
        请注意，这会制造出大量线程，并不是最佳的性能优化方案。
        虽然不适合大规模部署，但这一方案可以在无需额外开发的情况下支持在异步环境中调用，快速验证业务逻辑。
        """
        loop = asyncio.get_running_loop()
        for block in await self.run_in_executor(self.call, *args, **kwargs):
            yield block

    async def run_in_executor(self, sync_function: Callable, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func = partial(sync_function, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func)

    def clone(self, **kwargs) -> "Runnable":
        """
        克隆当前对象，返回一个新的对象。

        如果提供 kwargs 参数，你就可以在克隆的同时修改对象属性。
        """
        return self.__class__(
            threads_group=kwargs.pop("threads_group") or self.threads_group,
            continue_running=kwargs.pop("continue_running") or self.continue_running,
            **kwargs
        )
