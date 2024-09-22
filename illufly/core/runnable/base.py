import asyncio
import inspect

from typing import Union, List, Dict, Any, Callable
from abc import ABC, abstractmethod
from functools import partial

from .binding_manager import BindingManager
from .executor_manager import ExecutorManager
from ...io import log


class Runnable(ABC, ExecutorManager, BindingManager):
    """
    实现基本可运行类，定义了可运行的基本接口。
    只要继承该类，就可以作为智能体的工具使用。

    实现机制：
    - 支持 TextBlock 流式输出句法
    - 实现 __call__ 方法，来简化流输出调用
    - 通过 _last_input 保存当次调用的输入结果，并使用 last_input 属性方法来获取
    - 通过 _last_output 保存当次调用的输出结果，并使用 last_output 属性方法来获取
    - 支持 bind 方法，来动态发布变量
    - 支持 bound_vars 方法，来动态绑定变量
    - 支持 call 同步方法调用
    - 支持 async_call 方法调用，并在 Runnable 中已实现默认版本
    - 支持 stop 方法来停止仍在进行的异步调用

    什么时候直接从 Runnable 继承？
    - 如果需要支持流式输出
    - 仅仅做数据处理，而没有过多服务端调度逻辑

    什么时候转而使用BaseAgent？
    - 如果需要在多智能体中协同处理
    - 如果包含服务端调度逻辑

    """

    def __init__(
        self,
        *,
        continue_running: bool=True,
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
        """
        ExecutorManager.__init__(self, **kwargs)
        BindingManager.__init__(self, **kwargs)

        self.continue_running = continue_running

    def __call__(self, *args, verbose:bool=False, handler:Callable=None, **kwargs):
        handler = handler or log
        return handler(self, *args, verbose=verbose, **kwargs)

    @property
    def is_running(self):
        return self.continue_running

    def halt(self):
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
