import os
import asyncio

from typing import Union, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from functools import partial


class Runnable(ABC):
    # 声明一个类属性字典，用于存储不同组的线程池
    executors = {}

    def __init__(self, threads_group: str=None):
        """
        可以在环境变量中配置默认的线程池数量。
        例如：
        DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
        可以配置CHAT_OPENAI线程池的最大线程数为10。
        """
        self.threads_group = threads_group or "DEFAULT"
        if self.threads_group not in self.executors:
            max_workers = int(os.getenv(f"DEFAULT_MAX_WORKERS_{self.threads_group.upper()}", 5))
            self.executors[self.threads_group] = ThreadPoolExecutor(max_workers=max_workers)
        self.executor = self.executors[self.threads_group]

    @abstractmethod
    def call(self, *args, **kwargs):
        yield "hello"

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
