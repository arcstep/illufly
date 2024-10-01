import asyncio
import inspect

from typing import Union, List, Dict, Any, Callable, Generator, AsyncGenerator
from abc import ABC, abstractmethod
from functools import partial

from .executor_manager import ExecutorManager
from ...io import log


class Runnable(ABC, ExecutorManager):
    """
    实现基本可运行类，定义了可运行的基本接口。
    只要继承该类，就可以作为智能体的工具使用。

    实现机制：
    - 支持 EventBlock 流式输出句法
    - 实现 __call__ 方法，来简化流输出调用
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
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
        """
        ExecutorManager.__init__(self, **kwargs)

        self.continue_running = continue_running
        self.handlers = handlers
        self.verbose = False

        self._last_input = None
        self._last_output = None

    @property
    def last_input(self):
        return self._last_input

    @property
    def last_output(self):
        return self._last_output

    def __call__(
        self,
        *args,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        **kwargs
    ):
        handlers = handlers or self.handlers or [log]
        if any(inspect.iscoroutinefunction(handler) for handler in handlers):
            return self._handle_async_call(*args, verbose=verbose, handlers=handlers, **kwargs)
        else:
            return self._handle_sync_call(*args, verbose=verbose, handlers=handlers, **kwargs)

    def _handle_sync_call(
        self,
        *args,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        **kwargs
    ):
        self.verbose = verbose
        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            generator = self.call(*args, **kwargs)
            for block in generator:
                block.runnable_info = self.runnable_info
                for handler in handlers:
                    if not inspect.iscoroutinefunction(handler):
                        handler(block, verbose=verbose, **kwargs)
            return self.last_output
        else:
            raise ValueError("handlers 必须是可调用的列表")

    async def _handle_async_call(
        self,
        *args,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        **kwargs
    ):
        self.verbose = verbose
        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            async for block in self.async_call(*args, **kwargs):
                block.runnable_info = self.runnable_info
                tasks = []
                for handler in handlers:
                    resp = handler(block, verbose=verbose, **kwargs)
                    if inspect.isawaitable(resp):
                        tasks.append(asyncio.create_task(resp))
                if tasks:
                    await asyncio.gather(*tasks)
            return self.last_output
        else:
            raise ValueError("handlers 必须是可调用的列表")

    @property
    def is_running(self):
        return self.continue_running
    
    @property
    def runnable_info(self):
        return {
            "class_name": self.__class__.__name__,
        }

    def halt(self):
        self.continue_running = False

    @abstractmethod
    def call(self, *args, **kwargs):
        """
        这是同步调用的主入口，默认须实现该方法。
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

    def _is_running_in_jupyter(self):
        try:
            from IPython import get_ipython
            if 'IPKernelApp' not in get_ipython().config:
                return False
        except Exception:
            return False
        return True
