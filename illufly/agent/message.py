import json
from typing import Union, Dict, Any, List, Tuple

from ..hub import Template

class Message:
    def __init__(self, role: str, content: Union[str, Template]):
        self.role = role
        self.content = content

    def __str__(self):
        return f"{self.role}: {self.content}"

    def __repr__(self):
        return f"Message(role={self.role}, content={self.content})"
    
    @property
    def message(self):
        return {
            "role": self.role,
            "content": self.text
        }

    @property
    def text(self):
        if isinstance(self.content, Template):
            return self.content.get_prompt()
        return self.content

    @property
    def json(self):
        return json.dumps({
            "role": self.role,
            "content": self.content
        })

class Messages:
    def __init__(self, messages: Union[Message, str, Template, Tuple[str, Union[str, Template]], List[Union[Message, str, Template, dict, Tuple[str, Union[str, Template]]]]]):
        self._messages = messages
        self.messages = []
        self._convert_to_message_list()

    def _convert_to_message_list(self) -> None:
        if not isinstance(self._messages, list):
            self._messages = [self._messages]
        for i, msg in enumerate(self._messages):
            self.messages.append(self._convert_to_message(msg, i))

    def _convert_to_message(self, msg: Union[Message, str, Template, dict, Tuple[str, Union[str, Template]]], index: int) -> Message:
        if isinstance(msg, Message):
            return msg
        elif isinstance(msg, str):
            role = self._determine_role(index)
            return Message(role=role, content=msg)
        elif isinstance(msg, Template):
            role = self._determine_role(index)
            return Message(role=role, content=msg)
        elif isinstance(msg, dict):
            if msg.get('role') == 'ai':
                msg['role'] = 'assistant'
            return Message(role=msg.get('role', 'user'), content=msg.get('content', ''))
        elif isinstance(msg, tuple) and len(msg) == 2:
            role, content = msg
            if role == 'ai':
                role = 'assistant'
            if role in ['user', 'assistant', 'system']:
                return Message(role=role, content=content)
            else:
                raise ValueError("Unsupported role type in tuple")
        else:
            raise ValueError("Unsupported message type")

    def _determine_role(self, index: int) -> str:
        if index == 0:
            return 'system'
        elif self.messages[0].role == 'system' and index == 1:
            return 'user'
        else:
            last_role = self.messages[-1].role if self.messages else 'user'
            return 'assistant' if last_role == 'user' else 'user'

    def __str__(self):
        return "\n".join([str(message) for message in self.messages])

    def __repr__(self):
        return f"Messages(messages={self.messages})"
    
    def to_list(self):
        return [msg.message for msg in self.messages]
    
    def to_json(self):
        return [msg.json for msg in self.messages]
