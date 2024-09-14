import os
import asyncio
import copy

from typing import Union, List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from functools import partial
import re
import pandas as pd

from ..hub import Template


class Dataset:
    def __init__(self, df: Union[pd.DataFrame]=None, desc: str=None):
        self.df = df
        self.desc = desc
    
    def __str__(self):
        return self.desc

    def __repr__(self):
        return f"Dataset(desc={self.desc})"

class Knowledge:
    def __init__(self, text: str):
        self.text = text

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"Knowledge(text={self.text})"

    def __eq__(self, other):
        if isinstance(other, Knowledge):
            return self.text == other.text
        return False

    def __hash__(self):
        return hash(self.text)

class Runnable(ABC):
    """
    可运行的抽象类，定义了可运行的基本接口。

    基于 Runnable 子类可以实现多智能体协作。
    """

    # 声明一个类属性字典，用于存储不同组的线程池
    executors = {}

    def __init__(
        self,
        threads_group: str=None,
        memory: List[Union[str, "Template", Dict[str, Any]]] = None,
        k: int = 10,
        end_chk: bool = False,
        knowledge: List[str] = None,
        data: Dict[str, Any] = None,
        task: str = None,
        draft: str = None,
        outline: str = None,
        state: Dict[str, Any] = None,
        **kwargs
    ):
        """
        :param memory: 初始化记忆。
        :param k: 记忆轮数。

        self.locked_items 是锁定的记忆条数，每次对话时将会保留。

        对于使用多线程实现的外部调用，可以在环境变量中配置默认的线程池数量。
        例如：
        DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
        可以配CHAT_OPENAI线程池的��大线程数为10。
        """
        self.threads_group = threads_group or "DEFAULT"
        if self.threads_group not in self.executors:
            max_workers = int(os.getenv(f"DEFAULT_MAX_WORKERS_{self.threads_group.upper()}", 5))
            self.executors[self.threads_group] = ThreadPoolExecutor(max_workers=max_workers)
        self.executor = self.executors[self.threads_group]

        self.input_memory = memory or []
        self.memory = []

        self.locked_items = None
        self.remember_rounds = k
        self.end_chk = end_chk
        self.knowledge = knowledge or []
        self.data = data or {}
        self.state = state or {}

        self._task = task or None
        self._draft = draft or None
        self._outline = outline or None
    @property
    def desk(self):
        """
        这些属性允许其他对象读取，但修改需要专门的方法，例如`self.set_task`
        """
        return {
            "task": self._task,
            "draft": self._draft,
            "outline": self._outline,
            "output": self.output,
            "data": self.data,
            "knowledge": self.knowledge,
            "state": self.state,
        }

    def set_task(self, task: str):
        self._task = task

    def set_draft(self, draft: str):
        self._draft = draft

    def set_outline(self, outline: str):
        self._outline = outline

    @property
    def desk_vars_in_template(self):
        """
        确定哪些变量被提示语模板动态使用。
        """
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

    def confirm_memory_init(self):
        """
        确认记忆被正确初始化过。
        """
        if not self.memory and self.input_memory:
            for x in self.convert_prompt_to_messages(self.input_memory):
                self.memory.append(x)
        return self.memory

    def convert_prompt_to_messages(self, prompt: Union[str, List[Union[str, dict, Template]]]):
        """
        将 prompt 转换为消息列表。
        """
        # prompt 是 str
        if isinstance(prompt, str):
            return [{'role': 'system', 'content': prompt}]

        # 
        if isinstance(prompt, Template):
            return [{'role': 'system', 'content': prompt.get_prompt()}]

        # prompt 是 str 列表，且只有一个元素
        if isinstance(prompt, list) and len(prompt) == 1 and isinstance(prompt[0], str):
            return [{'role': 'system', 'content': prompt[0]}]

        messages = []
        roles = ['user', 'assistant']
        for i, element in enumerate(prompt):
            if i > 0 and messages[0].get('role') == 'system':
                _i = i + 1
            else:
                _i = i
            if isinstance(element, dict):
                messages.append(element)
            elif isinstance(element, str):
                messages.append({'role': roles[_i % 2], 'content': element})
            elif isinstance(element, Template):
                # 为Template指定desk引用
                # 这一步很重要，是动态合成提示语模板的关键
                #
                element.desk = self.desk
                #

                role = 'system' if _i == 0 else roles[_i % 2]
                messages.append({'role': role, 'content': element.get_prompt()})

        return messages

    @property
    def output(self):
        return self.memory[-1]['content'] if self.memory else ""
    
    def clone(self):
        """
        原则上，只应当修改 Runnable 中的数据，以便子类在执行 clone 方法时可以覆盖到所有需要克隆的数据。

        !! 如果子类中有单独保存的数据，就应当覆写 clone 方法。(实际上你应当遵循上述原则)
        """
        new_obj = self.__class__(
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
        # new_obj.memory = copy.deepcopy(self.memory)
        return new_obj

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if prompt:
            if isinstance(prompt, str):
                new_memory = [{"role": "user", "content": prompt}]
            else:
                new_memory = prompt
            self.memory.extend(new_memory)
        else:
            new_memory = []
        return new_memory

    def remember_response(self, response: Union[str, List[dict]]):
        if response:
            if isinstance(response, str):
                new_memory = [{"role": "assistant", "content": response}]
            else:
                new_memory = response
            self.memory.extend(new_memory)
        else:
            new_memory = []
        return new_memory

    def get_chat_memory(self, remember_rounds:int=None):
        """
        优化聊天记忆。

        1. 如果记忆中包含系统消息，则只保留前 locked_items 条消息。
        2. 否则，只保留最后 k 轮对话消息。
        3. 如果有准备好的知识，则将知识追加到消息列表中。
        4. TODO: 移除工具回调等过程细节消息。
        5. TODO: 将对话历史制作成对应摘要，以提升对话质量。
        6. TODO: 根据问题做「向量检索」，提升对话的理解能力。
        7. TODO: 根据问题做「概念检索」，提升对话的理解能力。

        """
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_memory = self.memory[:self.locked_items]
            new_memory += self.memory[self.locked_items:][-final_k:]
        else:
            new_memory = self.memory[-final_k:]

        self.add_knowledge(new_memory)

        return new_memory

    # 管理知识
    def add_knowledge(self, new_memory: List[Any]):
        """
        将知识库中的知识追加到消息列表中。
        """
        existing_contents = {msg['content'] for msg in new_memory if msg['role'] == 'user'}
        
        for kg in self.get_knowledge():
            content = f'已知：{kg}'
            if content not in existing_contents:
                new_memory.extend([{
                    'role': 'user',
                    'content': content
                },
                {
                    'role': 'assistant',
                    'content': 'OK, 我将利用这个知识回答后面问题。'
                }])
        return new_memory

    def get_knowledge(self, filter: str=None):
        if filter:
            return [kg.text for kg in self.knowledge if re.search(filter, kg.text)]
        else:
            return [kg.text for kg in self.knowledge]

    def clear_knowledge(self):
        self.knowledge.clear()

    # 管理数据集
    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
    
    def get_dataset_names(self):
        return list(self.data.keys())
    
    def clear_dataset(self):
        self.data.clear()



    @abstractmethod
    def call(self, prompt: Union[str, List[dict], "Template"], *args, **kwargs):
        # yield "hello"
        pass
    
    async def async_call(self, *args, **kwargs):
        loop = asyncio.get_running_loop()
        for block in await self.run_in_executor(self.call, *args, **kwargs):
            yield block

    async def run_in_executor(self, sync_function, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func = partial(sync_function, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func)

    @classmethod
    def monitor_executors(cls):
        info = {}
        for group, executor in cls.executors.items():
            active_threads = len(executor._threads)
            max_workers = executor._max_workers
            # 计算等待队列中的任务数量
            waiting_threads = executor._work_queue.qsize()
            info[group] = {
                "max_workers": max_workers,
                "used_workers": active_threads,
                "waiting_threads": waiting_threads
            }
        return info

    @classmethod
    def shutdown_executors(cls):
        for executor in cls.executors.values():
            executor.shutdown(wait=True)

