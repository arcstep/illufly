import os
import asyncio

from typing import Union, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from functools import partial

from .state import State

class Runnable(ABC):
    """
    可运行的抽象类，定义了可运行的基本接口。

    基于 Runnable 子类可以实现多智能体协作。
    """

    # 声明一个类属性字典，用于存储不同组的线程池
    executors = {}

    def __init__(self, threads_group: str=None, memory: List[Dict[str, Any]] = None, k: int = 1, end_chk: bool = False):
        """
        :param memory: 初始化记忆。
        :param k: 记忆轮数。

        self.locked_items 是锁定的记忆条数，每次对话时将会保留。

        对于使用多线程实现的外部调用，可以在环境变量中配置默认的线程池数量。
        例如：
        DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
        可以配置CHAT_OPENAI线程池的最大线程数为10。
        """
        self.threads_group = threads_group or "DEFAULT"
        if self.threads_group not in self.executors:
            max_workers = int(os.getenv(f"DEFAULT_MAX_WORKERS_{self.threads_group.upper()}", 5))
            self.executors[self.threads_group] = ThreadPoolExecutor(max_workers=max_workers)
        self.executor = self.executors[self.threads_group]

        self.memory = memory or []
        self.locked_items = None
        self.remember_rounds = k
        self.end_chk = end_chk
        self.state = State()

    @property
    def output(self):
        return self.memory[-1]['content'] if len(self.memory) > 0 else ""

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if isinstance(prompt, str):
            new_memory = {"role": "user", "content": prompt}
        else:
            new_memory = prompt[-1]
        self.memory.append(new_memory)
        return [new_memory]

    def remember_response(self, response: Union[str, List[dict]]):
        if isinstance(response, str):
            new_memory = [{"role": "assistant", "content": response}]
        else:
            new_memory = response
        self.memory.extend(new_memory)
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

    def add_knowledge(self, new_memory: List[Any]):
        """
        将知识库中的知识追加到消息列表中。
        """
        existing_contents = {msg['content'] for msg in new_memory if msg['role'] == 'user'}
        
        for kg in self.state.get_knowledge():
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

    @abstractmethod
    def call(self, *args, **kwargs):
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
