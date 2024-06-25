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

from ..config import get_folder_root, get_default_user, get_folder_history

def create_session_id(user_id: str = "default_user"):
    now = datetime.datetime.now()
    random_digits = random.randint(1000, 9999)  # 生成一个四位的随机数
    return now.strftime(f"%Y-%m-%d-%H%M%S-{random_digits}-{user_id}")

def parse_session_id(session_id: str):
    try:
        year, month, day, _time_str, _random_digits, user_id = session_id.split('-')
        parsed = {
            "year": int(year),
            "month": int(month),
            "day": int(day),
            "session_id": session_id,
            "user_id": user_id
        }
        if None in parsed.values():
            raise ValueError(f"None value found in parsed session_id: {session_id}")
        return parsed
    except ValueError:
        raise ValueError(f"Unable to parse session_id: {session_id}")

class LocalFileStore(BaseChatMessageHistory):
    """
    本地文件存储。
    """
    
    @property
    def file_path(self):
        """
        文件路径的构造规则：{history_folder}/{year}/{session_id}.json
        """
        parsed = parse_session_id(self.session_id)
        path = os.path.join(
            self.history_folder,
            str(parsed['year']),
            parsed['session_id'])
        return Path(f"{path}.json")

    def __init__(
        self,
        session_id: str = None,
        history_folder: str = None,
        user_id: str = None,
    ):
        self.user_id = user_id or get_default_user()
        self.session_id = session_id or create_session_id(self.user_id)
        self.history_folder = history_folder or os.path.join(get_folder_root(), self.user_id, get_folder_history())

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

