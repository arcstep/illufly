import asyncio
import inspect
import uuid

from typing import Union, List, Dict, Any, Callable, Generator, AsyncGenerator
from abc import ABC, abstractmethod
from functools import partial

from .executor_manager import ExecutorManager
from .binding_manager import BindingManager
from ...io import log, EventBlock, event_stream
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

    calling_id 是 Runnable 的属性，用于标识一次调用。
    如果在 Runnable 中调用另一个 Runnable，则需要将该 Runnable 的 calling_id 传递给被调用的 Runnable。
    这样，即使在一次调用中嵌套了多层的 Runnable，也可以将当次调用中的事件收集到当前调用的上下文，在下次恢复时，
    可以看到当时的完整调用场景。
    """
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "name": "Runnable 名称，默认为 {类名}.{id}",
            "handlers": "EventBlock 迭代器处理函数列表，默认为 [log]，当调用 call 方法时，会使用该列表中的函数逐个处理 EventBlock",
            "block_processor": "在 yield 之前将 EventBlock 事件转换为新的格式，在 __call__ 方法的输出生成器时使用",
            **ExecutorManager.allowed_params(),
            **BindingManager.allowed_params(),
        }
    
    @classmethod
    def help(cls):
        """
        返回当前可用的参数列表。
        """
        return f'{cls.__doc__}\n\n{cls.__name__} 参数列表：\n' + "\n".join([f"- {k}: {v}" for k, v in cls.allowed_params().items()])

    def __init__(
        self,
        *,
        name: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        block_processor: Callable = None,
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
        self.handlers = [log] if handlers is None else handlers
        self.block_processor = block_processor
        self.verbose = False

        self.calling_id = None
        self._last_output = None

        BindingManager.__init__(self, **filter_kwargs(kwargs, BindingManager.allowed_params()))

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.name == other.name
        return False

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
        return str(uuid.uuid1())

    def create_event_block(self, *args, **kwargs):
        return EventBlock(*args, runnable_info=self.runnable_info, **kwargs)

    def __call__(
        self,
        *args,
        verbose: bool = False,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        block_processor: Callable = None,
        generator: str = None,
        action: str = None,
        calling_id: str = None,
        **kwargs
    ):
        if action and not hasattr(self, action):
            raise AttributeError(f"方法 '{action}' 不存在于实例中")

        self._last_output = None
        self.calling_id = calling_id or self.build_calling_id()

        block_processor = block_processor or self.block_processor or event_stream
        self.continue_running = True
        _handlers = handlers if handlers is not None else self.handlers
        _verbose = self.verbose or verbose

        if generator == "async" or any(inspect.iscoroutinefunction(handler) for handler in _handlers):
            method = getattr(self, action) if action else self.async_call

            if generator:
                return self.generate_async_call(
                    *args,
                    verbose=_verbose,
                    handlers=_handlers,
                    action_method=method,
                    block_processor=block_processor,
                    **kwargs
                )
            else:
                return self.handle_async_call(
                    *args,
                    verbose=_verbose,
                    handlers=_handlers,
                    action_method=method,
                    **kwargs
                )
        else:
            method = getattr(self, action) if action else self.call

            if generator:
                return self.generate_sync_call(
                    *args,
                    verbose=_verbose,
                    handlers=_handlers,
                    action_method=method,
                    block_processor=block_processor,
                    **kwargs
                )
            else:
                return self.handle_sync_call(
                    *args,
                    verbose=_verbose,
                    handlers=_handlers,
                    action_method=method,
                    **kwargs
                )

    def handle_block(self, block, handlers, verbose, **kwargs):
        if isinstance(block, str):
            block = self.create_event_block("text", block)
        elif not isinstance(block, EventBlock):
            block = self.create_event_block("text", str(block))

        block.runnable_info.update({"calling_id": self.calling_id})

        for handler in handlers:
            if not inspect.iscoroutinefunction(handler):
                handler(block, verbose=verbose, **kwargs)

    async def async_handle_block(self, block, handlers, verbose, **kwargs):
        if isinstance(block, str):
            block = self.create_event_block("text", block)
        elif not isinstance(block, EventBlock):
            block = self.create_event_block("text", str(block))

        block.runnable_info.update({"calling_id": self.calling_id})

        tasks = []
        for handler in handlers:
            resp = handler(block, verbose=verbose, **kwargs)
            if inspect.isawaitable(resp):
                tasks.append(asyncio.create_task(resp))
        if tasks:
            await asyncio.gather(*tasks)

    def generate_sync_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        block_processor: Callable = None,
        **kwargs
    ):
        block = self.create_event_block("runnable", self.name)
        self.handle_block(block, handlers, verbose, **kwargs)
        yield block_processor(block, verbose=verbose, **kwargs)

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)
            if isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        return

                    self.handle_block(block, handlers, verbose, **kwargs)
                    block_text = block_processor(block, verbose=verbose, **kwargs)
                    if block_text:
                        yield block_text
            else:
                block = self.create_event_block("text", str(resp))
                self.handle_block(block, handlers, verbose, **kwargs)
                block_text = block_processor(block, verbose=verbose, **kwargs)
                if block_text:
                    yield block_text
        else:
            raise ValueError("handlers 必须是Callable列表")

    def handle_sync_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        **kwargs
    ):
        block = self.create_event_block("runnable", self.name)
        self.handle_block(block, handlers, verbose, **kwargs)

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)
            if isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        return
                    self.handle_block(block, handlers, verbose, **kwargs)
            else:
                block = self.create_event_block("text", str(resp))
                self.handle_block(block, handlers, verbose, **kwargs)
        else:
            raise ValueError("handlers 必须是Callable列表")

        return self.last_output

    async def generate_async_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        block_processor: Callable = None,
        **kwargs
    ):
        block = self.create_event_block("runnable", self.name)
        await self.async_handle_block(block, handlers, verbose, **kwargs)
        yield block_processor(block, verbose=verbose, **kwargs)

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)

            if isinstance(resp, AsyncGenerator):
                async for block in resp:
                    if not self.continue_running:
                        return
                    await self.async_handle_block(block, handlers, verbose, **kwargs)
                    block_text = block_processor(block, verbose=verbose, **kwargs)
                    if block_text:
                        yield block_text
                        await asyncio.sleep(0)
            elif isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        return
                    await self.async_handle_block(block, handlers, verbose, **kwargs)
                    block_text = block_processor(block, verbose=verbose, **kwargs)
                    if block_text:
                        yield block_text
                        await asyncio.sleep(0)
            else:
                block = self.create_event_block("text", str(resp))
                await self.async_handle_block(block, handlers, verbose, **kwargs)
                block_text = block_processor(block, verbose=verbose, **kwargs)
                if block_text:
                    yield block_text
                    await asyncio.sleep(0)
        else:
            raise ValueError("handlers 必须是Callable列表")

    async def handle_async_call(
        self,
        *args,
        verbose: bool = False,
        calling_id: str = None,
        handlers: List[Union[Callable, Generator, AsyncGenerator]] = None,
        action_method: Callable = None,
        **kwargs
    ):
        block = self.create_event_block("runnable", self.name)
        await self.async_handle_block(block, handlers, verbose, **kwargs)

        if isinstance(handlers, list) and all(callable(handler) for handler in handlers):
            resp = action_method(*args, **kwargs)
            if isinstance(resp, AsyncGenerator):
                async for block in resp:
                    if not self.continue_running:
                        return
                    await self.async_handle_block(block, handlers, verbose, **kwargs)
            elif isinstance(resp, Generator):
                for block in resp:
                    if not self.continue_running:
                        return
                    await self.async_handle_block(block, handlers, verbose, **kwargs)
            else:
                block = self.create_event_block("text", str(resp))
                await self.async_handle_block(block, handlers, verbose, **kwargs)
        else:
            raise ValueError("handlers 必须是Callable列表")

        return self.last_output

    @property
    def is_running(self):
        return self.continue_running
    
    @property
    def runnable_info(self):
        return {
            "name": self.name,
            "class_name": self.__class__.__name__,
            "calling_id": self.calling_id,
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
