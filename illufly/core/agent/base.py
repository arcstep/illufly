import asyncio
import copy
import inspect
import pandas as pd
import json

from typing import Union, List, Dict, Any, Callable
from abc import ABC, abstractmethod
from functools import partial

from .executor_manager import ExecutorManager
from .memory_manager import MemoryManager
from .knowledge_manager import KnowledgeManager
from ..template import Template
from ..dataset import Dataset

PYTHON_TO_JSON_TYPES = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
}

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
                if param_type in PYTHON_TO_JSON_TYPES:
                    param_type = PYTHON_TO_JSON_TYPES[param_type]
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
    
    @classmethod
    def tools_desc(cls, tools: List["Runnable"]):
        """
        描述所有可选工具的具体情况。
        """
        tools_list = ",\n".join([json.dumps(t.tool, ensure_ascii=False) for t in tools])
        return f'```json\n[{tools_list}]\n```'

    @classmethod
    def tools_selected(cls, tools: List["Runnable"]):
        """
        描述工具选中的具体情况。
        """
        action_output = {
            "index": "integer: index of selected function",
            "function": {
                "name": "(string): 填写选中参数名称",
                "parameters": "(json): 填��具体参数值"
            }
        }
        name_list = ",".join([a.name for a in tools])
        example = '\n'.join([
            '**工具函数输出示例：**',
            '```json',
            '[{"index": 0, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"广州\"}"}},',
            '{"index": 1, "function": {"name": "get_current_weather", "parameters": "{\"location\": \"上海\"}"}}]',
            '```'
        ])

        output = f'```json <tools-calling>\n[{json.dumps(action_output, ensure_ascii=False)}]\n```'

        return f'从列表 [{name_list}] 中选择一个或多个funciton，并按照下面的格式输出函数描述列表，描述每个函数的名称和参数：\n{output}\n{example}'

    @classmethod
    def dataset_desc(cls, data: Dict[str, "Dataset"]):
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
    

class Runnable(ABC, BaseTool, ExecutorManager):
    """
    实现基本可运行类，定义了可运行的基本接口。
    只要继承该类，就可以作为智能体的工具使用。
    """

    def __init__(
        self,
        # 线程组
        threads_group: str = None,
        # 是否自动停止
        continue_running=True,
        **kwargs
    ):
        """
        Runnable 的构造函数，主要包括：
        - 初始化线程组
        - 工具：作为工具的Runnable列表，在发现工具后是否执行工具的标记等
        """
        self.continue_running = continue_running

        ExecutorManager.__init__(self, threads_group)
        BaseTool.__init__(self, **kwargs)

    @property
    def is_running(self):
        return self.continue_running

    def start(self):
        self.continue_running = True

    def stop(self):
        self.continue_running = False

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

class BaseAgent(Runnable, KnowledgeManager, MemoryManager):
    """
    实现基础的智能体类，支持知识管理、记忆管理和变量的发布订阅机制。
    
    基于 BaseAgent 子类可以实现多智能体协作。
    """

    def __init__(
        self,
        *args,
        memory: List[Union[str, "Template", Dict[str, Any]]] = None,
        k: int = 10,
        desk: Dict[str, Any] = None,
        **kwargs
    ):
        desk = desk or {}
        self.task = desk.get('task', None)
        self.draft = desk.get('draft', None)
        self.outline = desk.get('outline', None)
        self.data = desk.get('data', {})
        self.state = desk.get('state', {})

        super().__init__(*args, **kwargs)
        MemoryManager.__init__(self, memory, k)
        KnowledgeManager.__init__(self, desk.get('knowledge', []))

    def clone(self, **kwargs) -> "BaseAgent":
        """
        克隆当前对象，返回一个新的对象。

        如果提供 kwargs 参数，你就可以在克隆的同时修改对象属性。
        """
        return self.__class__(
            # 以下为 ExecutorManager 的参数
            threads_group=kwargs.pop("threads_group") or self.threads_group,
            # 以下为 Runnable 的参数
            continue_running=kwargs.pop("continue_running") or self.continue_running,
            # 以下为 MemoryManager参数
            memory=kwargs.pop("memory") or copy.deepcopy(self.init_memory),
            # 以下为 BaseAgent 的参数
            k=kwargs.pop("k") or self.remember_rounds,
            desk=kwargs.pop("desk") or copy.deepcopy(self.desk),
            **kwargs
        )

    @property
    def desk(self) -> Dict[str, Any]:
        """
        使用工作台变量实现跨智能体变量传递。
        这是 BaseAgent 子类的实例对象多有的统一规格。

        obj.desk 是一个只读属性，可以访问工作台变量的字典，字典中的键值主要包括：

        | 变量       | 生命周期       | 详细说明 |
        |:----------|:-------------:|:-----------------------------------------------------|
        | knowledge | 可手工维护    | 检索增强，添加方法 add_knowledge(knowledge: List[str])    |
        | data      | 可手工维护    | 数据分析，添加执行方法 add_data(data: pandas.DataFrame)    |
        | task      | 运行时修改    | 提问或输入，大模型调用开始自动修改                |
        | output    | 运行时修改    | 结果或输出，大模型调用结束自动修改                |
        | draft     | 运行时修改    | 写作任务中已完成的草稿，例如扩写任务中自动修改      |
        | outline   | 运行时修改    | 扩写提纲，在扩写任务中自动生成                   |
        | state     | 定制时使用    | 以上不够用时，建议使用state字典来定制状态数据      |
        """
        return {
            "task": self.task,
            "draft": self.draft,
            "outline": self.outline,
            "data": self.data,
            "state": self.state,
            # knowledge 在 KnowledgeManager 中定义
            "knowledge": self._knowledge,
            # output 在 MemoryManager 中作为只读属性定义
            "output": self.output,
        }
    
    def set_task(self, task: str):
        self.task = task

    def set_draft(self, draft: str):
        self.draft = draft

    def set_outline(self, outline: str):
        self.outline = outline

    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
    
    def get_dataset_names(self):
        return list(self.data.keys())

class ToolAgent(BaseAgent):
    def __init__(self, func: Callable=None, **kwargs):
        super().__init__(func=func, **kwargs)
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"<Tool {self.name}: {self.description}>"

    def call(self, *args, **kwargs):
        for block in self.func(*args, **kwargs):
            yield block
