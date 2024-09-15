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
    def __init__(self, *, func: Callable = None, name: str = None, description: str = None, parameters: Dict[str, Any] = None, **kwargs):
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

    def dataset_desc(self, data: Dict[str, "Dataset"]):
        datasets = []
        for ds in data.keys():
            head = data[ds].df.head()
            example_md = head.to_markdown(index=False)
            datasets.append(textwrap.dedent(f"""
            ------------------------------
            **数据集名称：**
            {ds}
            
            **部份数据样例：**

            """) + example_md)

        return '\n'.join(datasets)
    

class Runnable(ABC, BaseTool, ExecutorManager, MemoryManager, KnowledgeManager):
    """
    可运行的抽象类，定义了可运行的基本接口。

    基于 Runnable 子类可以实现多智能体协作。
    """

    def __init__(
        self,
        # 线程组
        threads_group: str = None,
        # 记忆
        memory: List[Union[str, Template, Dict[str, Any]]] = None,
        k: int = 10,
        # 是否生成尾标
        end_chk: bool = False,
        # 工作台状态管理
        knowledge: List[str] = None,
        data: Dict[str, Any] = None,
        task: str = None,
        draft: str = None,
        outline: str = None,
        state: Dict[str, Any] = None,
        output: str = None,
        # 关于Runnable的工具管理
        tools=None,
        exec_tool=True, 
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 记忆：长期记忆、短期记忆
        - 工作台数据：知识库、数据、状态、任务、草稿、提纲
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
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

        self._tools = tools or []
        self.prepared_tools = []
        self.exec_tool = exec_tool

        BaseTool.__init__(self, **kwargs)

    @property
    def desk(self) -> Dict[str, Any]:
        """
        使用工作台变量实现跨智能体变量传递。
        这是 Runnable 子类的实例对象多有的统一规格。
        通过 obj.desk 可以访问工作台变量字典，这主要包括：

        | 变量      | 类型          | 修改 |
        |:----------|:-------------:|:------------------------------------------|
        | knowledge | 可手工维护    | 执行方法 add_knowledge(knowledge: List[str]) |
        | data      | 可手工维护    | 执行方法 add_data(data: pandas.DataFrame)    |
        | task      | 运行时自动修改 | 大模型调用开始自动修改                         |
        | output    | 运行时自动修改 | 大模型调用结束自动修改                         |
        | draft     | 运行时自动修改 | FromOutline 任务中自动修改                   |
        | outline   | 运行时自动修改 | FromOutline 任务中自动修改                   |
        | state     | 定制时使用    | 建议使用的可定制状态字典                       |
        """
        return {
            "knowledge": self._knowledge,
            "data": self.data,
            "task": self._task,
            "draft": self._draft,
            "outline": self._outline,
            "output": self.output,
            "state": self.state,
        }
    
    def set_task(self, task: str):
        self._task = task

    def set_draft(self, draft: str):
        self._draft = draft

    def set_outline(self, outline: str):
        self._outline = outline

    def clone(self, **kwargs) -> "Runnable":
        """
        克隆当前对象，返回一个新的对象。

        如果提供 kwargs 参数，你就可以在克隆的同时修改对象属性。
        """
        return self.__class__(
            self.threads_group or kwargs.pop("threads_group"),
            memory=copy.deepcopy(self.init_memory) or kwargs.pop("memory"),
            k=self.remember_rounds or kwargs.pop("k"),
            end_chk=self.end_chk or kwargs.pop("end_chk"),
            knowledge=copy.deepcopy(self._knowledge) or kwargs.pop("knowledge"),
            data=copy.deepcopy(self.data) or kwargs.pop("data"),
            state=copy.deepcopy(self.state) or kwargs.pop("state"),
            task=self._task or kwargs.pop("task"),
            draft=self._draft or kwargs.pop("draft"),
            outline=self._outline or kwargs.pop("outline"),
            exec_tool=self.exec_tool or kwargs.pop("exec_tool"),
            **kwargs
        )

    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
    
    def get_dataset_names(self):
        return list(self.data.keys())

    @property
    def toolkits(self):
        return self._tools + self.prepared_tools

    def get_tools_desc(self, tools: List["Runnable"]=None):
        if tools and (
            not isinstance(tools, list) or
            not all(isinstance(tool, Runnable) for tool in tools)
        ):
            raise ValueError("tools 必须是 Runnable 列表")
        _tools = tools or []
        return [t.tool for t in (self.toolkits + _tools)]

    @abstractmethod
    def call(self, prompt: Union[str, List[dict], Template], *args, **kwargs):
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

