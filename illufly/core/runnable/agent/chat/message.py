import json
import copy
from typing import Union, Dict, Any, List, Tuple

from ...template import Template

class Message:
    def __init__(self, role: str, content: Union[str, Template]):
        self.role = role
        self.content = content

    def __str__(self):
        return f"{self.role}: {self.content}"

    def __repr__(self):
        return f"Message(role={self.role}, content={self.content})"
    
    def to_dict(self, input_vars: Dict[str, Any]=None):
        return {
            "role": self.role,
            "content": self.to_text(input_vars)
        }

    def to_text(self, input_vars: Dict[str, Any]=None):
        if isinstance(self.content, Template):
            return self.content.format(input_vars)
        return self.content

    def to_json(self, input_vars: Dict[str, Any]=None):
        if isinstance(self.content, Template):
            content = self.content.format(input_vars)
        else:
            content = self.content
        return json.dumps({
            "role": self.role,
            "content": self.content
        })

class Messages:
    """
    Messages 类被设计为「隐藏类」，用来简化消息列表的管理，但并不作为交换类型出现在流程中。
    这主要是为了回避增加不必要的新概念。

    构造函数中的 messages 参数将作为原始的「只读对象」，被保存到 self.raw_messages 中。
    无论你提供的列表元素是字符串、模板、元组还是字典，都会在实例化完成后，生成 Message 对象列表，并被写入到 self.messages 中。
    但类似 {"role": xx, "content": yy} 这种消息列表，是通过 self.to_list 方法「动态提取」的，这主要是为了兼容 Template 对象的模板变量。
    """

    def __init__(
        self,
        messages: Union[
            Message,
            str,
            Template,
            Tuple[str, Union[str, Template]],
            List[Union[Message, str, Template, dict, Tuple[str, Union[str, Template]]]]
        ]=None
    ):
        self.raw_messages = messages or []

        if not isinstance(self.raw_messages, list):
            self.raw_messages = [self.raw_messages]

        self.messages = []
        for i, msg in enumerate(self.raw_messages):
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
            print("Unsupported message type: ", msg)
            raise ValueError("Unsupported message type")

    def _determine_role(self, index: int) -> str:
        if index == 0:
            return 'system'
        elif self.messages[0].role == 'system' and index == 1:
            return 'user'
        else:
            last_role = self.messages[-1].role if self.messages else 'user'
            return 'assistant' if last_role == 'user' else 'user'

    def clone(self):
        return Messages(copy.deepcopy(self.raw_messages))

    def __str__(self):
        return "\n".join([str(message) for message in self.messages])

    def __repr__(self):
        return f"<Messages({self.length} items)>"
    
    def to_list(self, input_vars: Dict[str, Any]=None):
        return [msg.to_dict(input_vars) for msg in self.messages]
    
    def to_json(self, input_vars: Dict[str, Any]=None):
        return [msg.to_json(input_vars) for msg in self.messages]
    
    @property
    def length(self):
        return len(self.messages)

    @property
    def input_vars(self):
        all_vars = set()
        for msg in self.messages:
            if isinstance(msg.content, Template):
                for v in msg.content.using_vars_list:
                    all_vars.add(v)
        return list(all_vars)

    def append(self, message: Union[Message, str, Template, dict, Tuple[str, Union[str, Template]]]):
        self.messages.append(self._convert_to_message(message, len(self.messages)))

    def extend(self, messages: Union[Message, str, Template, Tuple[str, Union[str, Template]], List[Union[Message, str, Template, dict, Tuple[str, Union[str, Template]]]]]):
        for msg in messages:
            self.append(msg)
    
    def last_content(self):
        if self.messages:
            return self.messages[-1].content
        else:
            return None

    @property
    def all_templates(self):
        """
        从消息列表中提取所有模板对象
        """
        if self.messages:
            return [msg.content for msg in self.messages if isinstance(msg.content, Template)]
        else:
            return []
