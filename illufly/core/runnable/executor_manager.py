import os
from concurrent.futures import ThreadPoolExecutor

class ExecutorManager:
    """
    对于使用多线程实现的外部调用，可以在环境变量中配置默认的线程池数量。
    例如：
    DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
    """
    executors = {}

    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "threads_group": "如果由 illufly 管理线程池实现并发或异步，则可以指定线程组名称，默认为 DEFAULT",
        }

    def __init__(self, threads_group: str = None, **kwargs):
        self.threads_group = threads_group or "DEFAULT"
        if self.threads_group not in self.executors:
            max_workers = int(os.getenv(f"DEFAULT_MAX_WORKERS_{self.threads_group.upper()}", 5))
            self.executors[self.threads_group] = ThreadPoolExecutor(max_workers=max_workers)
        self.executor = self.executors[self.threads_group]

    @classmethod
    def monitor_executors(cls):
        info = {}
        for group, executor in cls.executors.items():
            active_threads = len(executor._threads)
            max_workers = executor._max_workers
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