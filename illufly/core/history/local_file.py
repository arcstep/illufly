import os
import json

from typing import Union, List

from ...config import get_env
from .base import BaseHistory

class LocalFileHistory(BaseHistory):
    """基于文件的记忆管理"""

    def __init__(self, directory: str = None, **kwargs):
        super().__init__(**kwargs)
        self.directory = directory or get_env("ILLUFLY_LOCAL_FILE_MEMORY")

    def last_thread_id_count(self):
        all_thread_ids = self.list_threads()
        if all_thread_ids:
            ids = all_thread_ids[-1].split("-")
            return int(ids[-1]) + 1
        else:
            return 0

    # 列举所有记忆线
    def list_threads(self):
        memory_dir = self._get_history_dir()
        if not os.path.exists(memory_dir):
            return []
        file_list = [os.path.basename(file) for file in os.listdir(memory_dir) if file.endswith(".json") and not file.startswith(".")]
        thread_ids = [file.replace(".json", "") for file in file_list]

        def thread_id_key(thread_id):
            ids = thread_id.split("-")
            return f'{ids[0]}-{ids[-1]}'

        return sorted(thread_ids, key=thread_id_key)

    def save_memory(self, thread_id: str, memory: List[dict]):
        path = self._get_history_file_path(thread_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False)

    def load_memory(self, thread_id: Union[str, int]=None):
        """
        加载记忆。

        如果 thread_id 是字符串，则直接加载指定线程的记忆；
        如果 thread_id 是整数，则将其当作索引，例如 thread_id=-1 表示加载最近一轮对话的记忆。
        """
        path = None
        _thread_id = thread_id
        if isinstance(thread_id, str):
            path = self._get_history_file_path(thread_id)
        elif isinstance(thread_id, int):
            if self.list_threads():
                _thread_id = self.list_threads()[thread_id]
                path = self._get_history_file_path(_thread_id)

        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return _thread_id, json.load(f)

        return _thread_id, []

    def _get_history_dir(self):
        return os.path.join(self.directory, self.agent_class.upper(), self.agent_name)

    def _get_history_file_path(self, thread_id: str):
        if thread_id:
            return os.path.join(
                self._get_history_dir(),
                f"{thread_id}.json"
            )
        else:
            raise ValueError("thread_id MUST not be None")
