import os
import json

from typing import Union, List

from ....config import get_env
from .base import BaseEventsHistory

class LocalFileEventsHistory(BaseEventsHistory):
    """基于文件的事件管理"""

    def __init__(self, directory: str = None, **kwargs):
        self.directory = directory or get_env("ILLUFLY_LOCAL_FILE_EVENTS")

        super().__init__(**kwargs)

    # 列举所有事件
    def list_events_histories(self):
        if not os.path.exists(self.directory):
            return []
        file_list = [os.path.basename(file) for file in os.listdir(self.directory) if file.endswith(".json") and not file.startswith(".")]
        events_ids = [file.replace(".json", "") for file in file_list]

        return sorted(events_ids)

    def save_events_history(self):
        """
        根据 events_history_id 保存历史事件。
        先保存到 self.store 中，再保存到文件中。
        """
        events_history = self.store[self.events_history_id]

        path = self._get_history_file_path(self.events_history_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events_history, f, ensure_ascii=False)

    def load_events_history(self, events_history_id: Union[str, int]=None):
        """根据 events_history_id 加载历史事件"""
        path = None
        if events_history_id is None:
            _events_history_id = self.last_history_id
        else:
            _events_history_id = events_history_id
        self.events_history_id = _events_history_id

        if isinstance(_events_history_id, str):
            path = self._get_history_file_path(_events_history_id)
        elif isinstance(_events_history_id, int):
            all_events_histories = self.list_events_histories()
            if all_events_histories:
                _events_history_id = all_events_histories[_events_history_id]
                path = self._get_history_file_path(_events_id)

        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.store[_events_history_id] = json.load(f)
                return _events_history_id, self.store[_events_history_id]

        return _events_history_id, {}

    def _get_history_file_path(self, events_id: str):
        if events_id:
            return os.path.join(self.directory, f"{events_id}.json")
        else:
            raise ValueError("events_id MUST not be None")
