import json
import copy
import os
from typing import Union, Dict, Any, List, Tuple

from ..runnable import Runnable

class Message:
    def __init__(self, role: str, content: Union[str, Runnable], **kwargs):
        self.role = role
        self.content = content
        self.kwargs = kwargs

    def __str__(self):
        return f"{self.role}: {self.content.selected.format() if isinstance(self.content, Runnable) else self.content}"

    def __repr__(self):
        return f"Message(role={self.role}, content={self.content})"
    
    def to_dict(self, binding: Dict[str, Any]=None, style: str=None):
        def get_url(item, key, alt_key):
            return item.get(key, item[alt_key]['url'] if alt_key in item and 'url' in item[alt_key] else None)
        
        def get_unique_format(style, binding):
            if isinstance(self.content, list):
                contents = []
                for item in self.content:
                    content = {}
                    if isinstance(item, str):
                        content["text"] = item
                    elif isinstance(item, dict):
                        if item.get("audio") or "audio_url" in item:
                            content["audio"] = item.get("audio", get_url(item, "audio", "audio_url"))
                        if item.get("video") or "video_url" in item:
                            content["video"] = item.get("video", get_url(item, "video", "video_url"))
                        if item.get("image") or "image_url" in item:
                            content["image"] = item.get("image", get_url(item, "image", "image_url"))
                        if item.get("text") is not None:
                            content["text"] = item.get("text")
                    else:
                        raise ValueError("Resource must be a string or a dict")
                    contents.append(content)
                return contents
            elif isinstance(self.content, str):
                return [{"text": self.content}]
            elif isinstance(self.content, Runnable):
                return [{"text": self.content.selected.format(binding)}]
        
        if style == "openai_vl":
            content = [
                {
                    "type": k if k == "text" else k + "_url",
                    (k if k == "text" else k + "_url"): v if k == "text" else {"url": v}
                }
                for item in get_unique_format(style, binding)
                for k, v in item.items()
            ]
        elif style == "qwen_vl":
            content = get_unique_format(style, binding)
        else:
            unique_format = get_unique_format(style, binding)
            if unique_format:
                content = "\n".join([c['text'] for c in unique_format if 'text' in c])
            else:
                content = ""

        return {
            "role": self.role,
            "content": content,
            **self.kwargs
        }

    def to_text(self, binding: Dict[str, Any]=None):
        if isinstance(self.content, Runnable):
            return self.content.selected.format(binding)
        return self.content

    def to_json(self, binding: Dict[str, Any]=None):
        if isinstance(self.content, Runnable):
            content = self.content.selected.format(binding)
        else:
            content = self.content
        return json.dumps({
            "role": self.role,
            "content": self.content,
            **self.kwargs
        })

class Messages:
    """
    Messages 类被设计为「隐藏类」，用来简化消息列表的管理，但并不作为交换类型出现在流程中。
    这主要是为了回避增加不必要的新概念。

    构造函数中的 messages 参数将作为原始的「只读对象」，被保存到 self.raw_messages 中。
    无论你提供的列表元素是字符串、模板、元组还是字典，都会在实例化完成后，生成 Message 对象列表，并被写入到 self.messages 中。
    但类似 {"role": xx, "content": yy} 这种消息列表，是通过 self.to_list 方法「动态提取」的，这主要是为了兼容 PromptTemplate 对象的模板变量。
    """

    def __init__(
        self,
        messages: Any=None,
        style: str=None,
        binding: Dict[str, Any]=None
    ):
        self.raw_messages = messages or []
        self.style = style
        self.binding = binding or {}
        if not isinstance(self.raw_messages, list):
            self.raw_messages = [self.raw_messages]

        self.messages = []
        for i, msg in enumerate(self.raw_messages):
            self.messages.append(self._convert_to_message(msg, i))

    def _convert_to_message(self, msg: Any, index: int) -> Message:
        message = None
        if isinstance(msg, Message):
            message = msg
        elif isinstance(msg, Runnable):
            message = Message(role='system' if index == 0 else self._determine_role(index), content=msg)
        elif isinstance(msg, str):
            message = Message(role='user' if index == 0 else self._determine_role(index), content=msg)
        elif isinstance(msg, list):
            role = self._determine_role(index)
            message = Message(role=role, content=msg)
        elif isinstance(msg, dict):
            if msg.get('role') == 'ai':
                msg['role'] = 'assistant'
            message = Message(**msg) # 支持字典构造中其他键值，如工具回调等
        elif isinstance(msg, tuple):
            if len(msg) == 2 and msg[0] in ["ai", "assistant", "user"]:
                role, content = msg
                if role == 'ai':
                    role = 'assistant'
                message = Message(role=role, content=content)
            else:
                # 多模态格式
                role = self._determine_role(index)
                msgs = []
                for item in msg:
                    if isinstance(item, str):
                        if item in ["ai", "assistant"]:
                            role = "assistant"
                        elif item in ["user"]:
                            role = "user"
                        else:
                            ext = os.path.splitext(item)[1][1:]
                            if ext.lower() in ["png", "jpg", "gif", "jpeg"]:
                                msg_type = "image"
                            elif ext.lower() in ["mp4", "webm"]:
                                msg_type = "video"
                            else:
                                msg_type = "text"
                            msgs.append({
                                msg_type: item
                            })
                    # elif isinstance(item, Runnable):
                    #     msgs.append({"text": item})
                    else:
                        raise ValueError("Unsupported message type in tuple", msg)
                message = Message(role=role, content=msgs)
        else:
            raise ValueError("Unsupported message type", msg)
        
        return message

    def _determine_role(self, index: int) -> str:
        if index == 0:
            return 'system'
        elif self.messages[0].role == 'system' and index == 1:
            return 'user'
        else:
            last_role = self.messages[-1].role if self.messages else 'user'
            return 'assistant' if last_role == 'user' else 'user'

    def clone(self):
        return Messages(copy.deepcopy(self.raw_messages), style=self.style, binding=self.binding)

    def __str__(self):
        return "\n".join([str(message) for message in self.messages])

    def __repr__(self):
        return f"<Messages({self.length} items)>"
    
    def __getitem__(self, index: int):
        return self.messages[index]
    
    def __iter__(self):
        return iter(self.messages)
    
    def __len__(self):
        return self.length

    def __add__(self, other):
        if not isinstance(other, Messages):
            raise TypeError("Operands must be of type Messages")
        combined_messages = self.messages + other.messages
        return Messages(combined_messages, style=self.style, binding=self.binding)
    
    def to_list(self, binding: Dict[str, Any]=None, style: str=None):
        return [msg.to_dict({**self.binding, **(binding or {})}, (style or self.style)) for msg in self.messages]
    
    def to_json(self, binding: Dict[str, Any]=None, style: str=None):
        return [msg.to_json({**self.binding, **(binding or {})}, (style or self.style)) for msg in self.messages]
    
    @property
    def length(self):
        return len(self.messages)

    def append(self, message: Union[Message, str, Runnable, dict, Tuple[str, Union[str, Runnable]]]):
        self.messages.append(self._convert_to_message(message, len(self.messages)))

    def extend(self, messages: Union[Message, str, Runnable, Tuple[str, Union[str, Runnable]], List[Union[Message, str, Runnable, dict, Tuple[str, Union[str, Runnable]]]]]):
        for msg in messages:
            self.append(msg)

    @property
    def last_role(self):
        if self.messages:
            return self.messages[-1].role
        else:
            return None
    
    @property
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
            return [msg.content for msg in self.messages if isinstance(msg.content, Runnable)]
        else:
            return []

    def has_role(self, role: str):
        return any(msg.role == role for msg in self.messages)
