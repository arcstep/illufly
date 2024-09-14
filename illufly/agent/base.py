import asyncio
import copy
import inspect
import pandas as pd

from typing import Union, List, Dict, Any, Callable
from abc import ABC, abstractmethod
from functools import partial

from ..hub import Template
from .executor_manager import ExecutorManager
from .memory_manager import MemoryManager
from .knowledge_manager import KnowledgeManager
from .dataset import Dataset

class BaseTool:
    def __init__(self, *, func: Callable = None, name: str = None, description: str = None, parameters: Dict[str, Any] = None):
        self.func = func or self.call
        self.name = name or (func.__name__ if func else self.__class__.__name__)
        self.arguments = func.__annotations__ if func else {}
        self.description = description or (func.__doc__ if func and func.__doc__ else "")
        self.parameters = parameters

    @property
    def tool(self) -> Dict[str, Any]:
        if not self.parameters:
            self.parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            sig = inspect.signature(self.func)
            for name, param in sig.parameters.items():
                param_type = self.arguments.get(name, str).__name__
                self.parameters["properties"][name] = {
                    "type": param_type,
                    "description": param.default if param.default is not inspect.Parameter.empty else ""
                }
                if param.default is inspect.Parameter.empty:
                    self.parameters["required"].append(name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }

class Runnable(ABC, BaseTool, ExecutorManager, MemoryManager, KnowledgeManager):
    """
    可运行的抽象类，定义了可运行的基本接口。

    基于 Runnable 子类可以实现多智能体协作。
    """

    def __init__(
        self,
        threads_group: str = None,
        memory: List[Union[str, Template, Dict[str, Any]]] = None,
        k: int = 10,
        end_chk: bool = False,
        knowledge: List[str] = None,
        data: Dict[str, Any] = None,
        task: str = None,
        draft: str = None,
        outline: str = None,
        state: Dict[str, Any] = None,
        output: str = None,
        **kwargs
    ):
        """
        :param memory: 初始化记忆。
        :param k: 记忆轮数。

        self.locked_items 是锁定的记忆条数，每次对话时将会保留。

        对于使用多线程实现的外部调用，可以在环境变量中配置默认的线程池数量。
        例如：
        DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
        可以配CHAT_OPENAI线程池的最大线程数为10。
        """
        ExecutorManager.__init__(self, threads_group)
        MemoryManager.__init__(self, memory, k)
        KnowledgeManager.__init__(self, knowledge)
        self.end_chk = end_chk

        # desk 值，使用方法填充
        self.data = data or {}
        self.state = state or {}

        # desk 值，可设置
        self._task = task
        self._draft = draft
        self._outline = outline

        BaseTool.__init__(self, **kwargs)

    @property
    def desk(self) -> Dict[str, Any]:
        """
        这些属性允许其他对象读取，但修改需要专门的方法，例如`self.set_task`
        """
        return {
            "knowledge": self.knowledge,
            "data": self.data,
            "state": self.state,
            "task": self._task,
            "draft": self._draft,
            "outline": self._outline,
            "output": self.output,
        }

    def set_task(self, task: str):
        self._task = task

    def set_draft(self, draft: str):
        self._draft = draft

    def set_outline(self, outline: str):
        self._outline = outline

    @property
    def desk_vars_in_template(self) -> Dict[str, Any]:
        if self.input_memory:
            if isinstance(self.input_memory, Template):
                return self.input_memory.desk_vars_in_template
            elif isinstance(self.input_memory, list):
                _desk_vars_in_template = {}
                for x in self.input_memory:
                    if isinstance(x, Template):
                        _desk_vars_in_template.update(x.desk_vars_in_template)
                return _desk_vars_in_template
        return {}

    def clone(self) -> "Runnable":
        return self.__class__(
            self.threads_group,
            memory=copy.deepcopy(self.input_memory),
            k=self.remember_rounds,
            end_chk=self.end_chk,
            knowledge=copy.deepcopy(self.knowledge),
            data=copy.deepcopy(self.data),
            state=copy.deepcopy(self.state),
            task=self._task,
            draft=self._draft
        )

    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
    
    def get_dataset_names(self):
        return list(self.data.keys())

    @abstractmethod
    def call(self, prompt: Union[str, List[dict], Template], *args, **kwargs):
        pass

    async def async_call(self, *args, **kwargs):
        loop = asyncio.get_running_loop()
        for block in await self.run_in_executor(self.call, *args, **kwargs):
            yield block

    async def run_in_executor(self, sync_function: Callable, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func = partial(sync_function, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func)

