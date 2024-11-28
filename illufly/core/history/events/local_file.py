import os
import json

from typing import Union, List

from ....config import get_env
from .base import BaseEventsHistory

class LocalFileEventsHistory(BaseEventsHistory):
    """基于文件的事件管理"""

    def __init__(self, directory: str = None, **kwargs):
        super().__init__(**kwargs)
        self.directory = directory or get_env("ILLUFLY_LOCAL_FILE_EVENTS")

    # 列举所有事件
    def list_events(self):
        if not os.path.exists(self.directory):
            return []
        file_list = [os.path.basename(file) for file in os.listdir(self.directory) if file.endswith(".json") and not file.startswith(".")]
        events_ids = [file.replace(".json", "") for file in file_list]

        def events_id_key(events_id):
            ids = events_id.split("-")
            return f'{ids[0]}-{ids[1]}-{ids[-2]}'

        return sorted(events_ids, key=events_id_key)

    def save_events_history(self, events_history_id: str, events_history: List[dict]):
        """
        根据 events_history_id 保存历史事件。
        先保存到 self.store 中，再保存到文件中。
        """
        super().save_events_history(events_history_id, events_history)

        path = self._get_history_file_path(events_history_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events_history, f, ensure_ascii=False)

    def load_events_history(self, events_history_id: Union[str, int]=None):
        """根据 events_history_id 加载历史事件"""
        path = None
        _events_id = events_history_id
        if isinstance(events_history_id, str):
            path = self._get_history_file_path(events_history_id)
        elif isinstance(events_history_id, int):
            all_events = self.list_events()
            if all_events:
                _events_id = all_events[events_history_id]
                path = self._get_history_file_path(_events_id)

        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.store[_events_id] = json.load(f)
                return _events_id, json.load(f)

        return _events_id, []

    def _get_history_file_path(self, events_id: str):
        if events_id:
            return os.path.join(
                self.directory,
                f"{events_id}.json"
            )
        else:
            raise ValueError("events_id MUST not be None")
