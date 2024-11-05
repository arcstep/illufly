import asyncio
import inspect
import uuid

from typing import Union, List, Dict, Any, Callable, Generator, AsyncGenerator
from abc import ABC, abstractmethod
from functools import partial

from .executor_manager import ExecutorManager
from .binding_manager import BindingManager
from ...io import log, EventBlock
from ...utils import filter_kwargs, raise_invalid_params


class Runnable(ABC, ExecutorManager, BindingManager):
    """
    实现基本可运行类，定义了可运行的基本接口。
    只要继承该类，就可以作为智能体的工具使用。

    实现机制：
    - 支持 EventBlock 流式输出句法
    - 实现 __call__ 方法，来简化流输出调用
    - 支持 call 同步方法调用
    - 支持 async_call 方法调用，并在 Runnable 中已实现默认版本
    - 支持 绑定机制

    什么时候直接从 Runnable 继承？
    - 如果需要支持流式输出
    - 仅仅做数据处理，而没有过多服务端调度逻辑

    什么时候转而使用BaseAgent？
    - 如果需要在多智能体中协同处理
    - 如果包含服务端调度逻辑

    """
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "name": "Runnable 名称，默认为 {类名}.{id}",
            "handlers": "EventBlock 迭代器处理函数列表，默认为 [log]，当调用 call 方法时，会使用该列表中的函数逐个处理 EventBlock",
            **ExecutorManager.allowed_params(),
            **BindingManager.allowed_params(),
        }
    
    @classmethod
    def help(cls):
        """
        返回当前可用的参数列表。
        """
        return cls.allowed_params()

    def __init__(
        self,
        *,
        name: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())
        ExecutorManager.__init__(self, **filter_kwargs(kwargs, ExecutorManager.allowed_params()))

        self.name = name or f'{self.__class__.__name__}.{id(self)}'
        self.continue_running = True
        self.handlers = handlers or []
        self.verbose = False

        self.calling_events = []

        self._last_output = None

        BindingManager.__init__(self, **filter_kwargs(kwargs, BindingManager.allowed_params()))

    def __repr__(self):
        if self.__class__.__name__ in self.name:
            return f"<{self.name}>"
        else:
            return f"<{self.__class__.__name__} {self.name}>"

    @property
    def selected(self):
        """
        让 Runnable 对象与 Selector 的访问方式兼容。
        """
        return self

    @property
    def last_output(self):
        return self._last_output

    @property
    def provider_dict(self):
        local_dict = {
            "last_output": self.last_output,
        }
        return {
            **super().provider_dict,
            **{k:v for k,v in local_dict.items() if v is not None},
        }

    def build_calling_id(self):
        return str(uuid.uuid4())

    def collect_event(self, calling_id: str, event: EventBlock):
        """
        收集 EventBlock 数据
        """
        if not self.calling_events or self.calling_events[-1]["id"] != calling_id:
            self.calling_events.append({"id": calling_id, "events": []})
        self.calling_events[-1]["events"].append(event)

    def __call__(
        self,
        *args,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action: str = None,
        **kwargs
    ):
        self.continue_running = True
        handlers = handlers or self.handlers or [log]
        _verbose = self.verbose or verbose

        if any(inspect.iscoroutinefunction(handler) for handler in handlers):
            if action:
                if not hasattr(self, action):
                    raise AttributeError(f"方法 '{action}' 不存在于实例中")
                method = getattr(self, action)
            else:
                method = self.async_call

            return self.handle_async_call(*args, verbose=_verbose, handlers=handlers, action_method=method, **kwargs)
        else:
            if action:
                if not hasattr(self, action):
                    raise AttributeError(f"方法 '{action}' 不存在于实例中")
                method = getattr(self, action)
            else:
                method = self.call
            return self.handle_sync_call(*args, verbose=_verbose, handlers=handlers, action_method=method, **kwargs)

    def handle_sync_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        **kwargs
    ):
        self._last_output = None
        calling_id = calling_id or self.build_calling_id()

        def handle_block(block):
            self.collect_event(calling_id, block)
            if isinstance(block, str):
                block = EventBlock("text", block)
            elif not isinstance(block, EventBlock):
                block = EventBlock("text", str(block))
            block.runnable_info = self.runnable_info
            for handler in handlers:
                if not inspect.iscoroutinefunction(handler):
                    handler(block, verbose=verbose, **kwargs)

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)
            if isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        break
                    handle_block(block)
            else:
                block = EventBlock("text", str(resp))
                block.runnable_info = self.runnable_info
                handle_block(block)
        else:
            raise ValueError("handlers 必须是Callable列表")

        return self.last_output

    async def handle_async_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        **kwargs
    ):
        self._last_output = None
        calling_id = calling_id or self.build_calling_id()

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)
            tasks = []
            async def async_handle_block(block):
                self.collect_event(calling_id, block)
                if isinstance(block, str):
                    block = EventBlock("text", block)
                elif not isinstance(block, EventBlock):
                    block = EventBlock("text", str(block))
                block.runnable_info = self.runnable_info
                for handler in handlers:
                    resp = handler(block, verbose=verbose, **kwargs)
                    if inspect.isawaitable(resp):
                        tasks.append(asyncio.create_task(resp))
                if tasks:
                    await asyncio.gather(*tasks)

            if isinstance(resp, AsyncGenerator):
                async for block in resp:
                    if not self.continue_running:
                        break
                    await async_handle_block(block)
            elif isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        break
                    await async_handle_block(block)
            else:
                block = EventBlock("text", str(resp))
                block.runnable_info = self.runnable_info
                await async_handle_block(block)

            return self.last_output
        else:
            raise ValueError("handlers 必须是Callable列表")

        return self.last_output

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

    def bind_consumer(self, runnable, binding_map: Dict=None, dynamic: bool=False):
        """
        传递自身的 handlers 给下游 runnable。
        """
        super().bind_consumer(runnable, binding_map=binding_map, dynamic=dynamic)
        for handler in self.handlers:
            if handler not in runnable.handlers:
                runnable.handlers.append(handler)
