from typing import Union, List, Dict, Any
import copy
from ..hub import Template
from .message import Messages, Message

class MemoryManager:
    def __init__(self, memory: List[Union[str, "Template", Dict[str, Any]]] = None, k: int = 10):
        self.init_memory = Messages(memory)
        self.memory = []
        self.locked_items = self.init_memory.length
        self.remember_rounds = k

    def confirm_memory_init(self):
        if not self.memory and self.init_memory:
            self.memory = self.init_memory.to_list()
        return self.memory

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if prompt:
            if isinstance(prompt, str):
                new_memory = Messages([("user", prompt)])
            else:
                new_memory = Messages(prompt)

            self.memory.extend(new_memory.to_list())
            return new_memory.to_list()
        else:
            return []

    def remember_response(self, response: Union[str, List[dict]]):
        if response:
            if isinstance(response, str):
                new_memory = Messages([("assistant", response)])
            else:
                new_memory = Messages(response)

            self.memory.extend(new_memory.to_list())
            return new_memory.to_list()
        else:
            return []

    def get_chat_memory(self, remember_rounds: int = None, knowledge: List[str] = None):
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_messages = self.memory[:self.locked_items]
            new_messages += self.memory[self.locked_items:][-final_k:]
        else:
            new_messages = self.memory[-final_k:]
        # 调用 Runnable 类中的 append_knowledge_to_messages 方法
        final_memory = self._append_knowledge_to_messages(new_messages, knowledge)
        return final_memory.to_list()

    def _append_knowledge_to_messages(self, new_messages: List[Message], knowledge: List[str]):
        existing_contents = {msg['content'] for msg in new_messages if msg['role'] == 'user'}
        new_memory = Messages(new_messages)
        for kg in knowledge:
            content = f'已知：{kg}'
            if content not in existing_contents:
                new_memory.append([
                    ("user", content),
                    ("assistant", 'OK, 我将利用这个知识回答后面问题。')
                ])
        return new_memory

    @property
    def output(self):
        return self.memory[-1]['content'] if self.memory else ""