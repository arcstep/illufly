import os
import asyncio
from typing import Union, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod


class BaseCall(ABC):
    # 声明一个类属性字典，用于存储不同组的线程池
    executors = {}

    def __init__(self, threads_group: str=None):
        self.threads_group = threads_group or "DEFAULT"
        if self.threads_group not in self.executors:
            max_workers = int(os.getenv(f"DEFAULT_MAX_WORKERS_{self.threads_group.upper()}", 5))
            self.executors[self.threads_group] = ThreadPoolExecutor(max_workers=max_workers)
        self.executor = self.executors[self.threads_group]

    async def run_in_executor(self, sync_function, *args, **kwargs):
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(self.executor, sync_function, *args, **kwargs)
        return result

    @abstractmethod
    def call(self, *args, **kwargs):
        yield "hello"

    async def async_call(self, *args, **kwargs):
        loop = asyncio.get_running_loop()
        result = await self.run_in_executor(self.call, *args, **kwargs)
        for block in result:
            yield block

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

class BaseChat(BaseCall):
    def __init__(self, model: str=None, memory: List[Dict[str, Any]]=None):
        self.model = model
        self.memory = memory or []
        super().__init__(threads_group="base_llm")

    def add_prompt_to_memory(self, prompt: Union[str, List[dict]]):
        if isinstance(prompt, str):
            new_memory = {"role": "user", "content": prompt}
        else:
            new_memory = prompt[-1]
        self.memory.append(new_memory)
    
    def add_response_to_memory(self, response: Union[str, List[dict]]):
        if isinstance(response, str):
            new_memory = {"role": "assistant", "content": response}
        else:
            new_memory = response[-1]
        self.memory.append(new_memory)

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        self.add_prompt_to_memory(prompt)

        full_content = ""
        for block in self.generate(prompt, *args, **kwargs):
            yield block
            full_content += block.content

        self.add_response_to_memory(full_content)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        pass