import os
import json
import logging
import datetime
import random

from pathlib import Path
from typing import List

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import (
    BaseMessage,
    messages_from_dict,
    messages_to_dict,
)

def create_session_id(user_id: str = "default"):
    now = datetime.datetime.now()
    random_digits = random.randint(1000, 9999)  # 生成一个四位的随机数
    return now.strftime(f"%Y_%m_%d_%H%M%S_{user_id}_{random_digits}")    

def parse_session_id(session_id: str):
    try:
        year, month, day, _time_str, user_id, _random_digits = session_id.split('_')
        parsed = {
            "year": int(year),
            "month": int(month),
            "day": int(day),
            "user_id": user_id,
            "session_id": session_id,
        }
        if None in parsed.values():
            raise ValueError(f"None value found in parsed session_id: {session_id}")
        return parsed
    except ValueError:
        raise ValueError(f"Unable to parse session_id: {session_id}")

class LocalFileMessageHistory(BaseChatMessageHistory):
    """
    Chat message history that stores history in a local file.

    Args:
        file_path: path of the local file to store the messages.
    """
    
    # 希望入库到知识库的本地文件夹根目录
    _history_folder: str = "./history"
    
    @property
    def history_folder(self):
        return self._history_folder
    
    @property
    def file_path(self):
        """
        文件路径的构造规则：{history_folder}/{year}/{month}/{session_id}.json
        """
        parsed = parse_session_id(self.session_id)
        path = os.path.join(
            self.history_folder,
            str(parsed['year']),
            str(parsed['month']),
            parsed['session_id'])
        return Path(f"{path}.json")

    @history_folder.setter
    def history_folder(self, value):
        self._history_folder = os.path.abspath(value)

    def __init__(
        self,
        session_id: str = None,
        history_folder: str = None,
        user_id: str = None,
    ):
        if user_id is None:
            self.user_id = "default"
        else:
            self.user_id = user_id

        if session_id is None:
            self.session_id = create_session_id(self.user_id)
        else:
            self.session_id = session_id

        if history_folder is None:
            _history_folder = os.getenv("LANGCHAIN_CHINESE_HISTORY_FOLDER")
            if _history_folder is not None:
                self.history_folder = _history_folder
            else:
                self.history_folder = "./history"
        else:
            self.history_folder = history_folder

    @property
    def messages(self) -> List[BaseMessage]:  # type: ignore
        """Retrieve the messages from the local file"""
        if not self.file_path.exists():
            return []
        items = json.loads(self.file_path.read_text())
        all_messages = messages_from_dict(items)
        return all_messages

    def add_message(self, message: BaseMessage) -> None:
        """Append the message to the record in the local file"""
        all_messages = messages_to_dict(self.messages)
        all_messages.append(messages_to_dict([message])[0])
        
        # 如果不存在就创建文件
        file_path = self.file_path
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True)
        if not file_path.exists():
            file_path.touch()

        file_path.write_text(json.dumps(all_messages, indent=4, ensure_ascii=False))

    def clear(self) -> None:
        """Clear session memory from the local file"""
        file_path = self.file_path
        if file_path.exists():
            file_path.write_text(json.dumps([]))
