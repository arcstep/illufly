from typing import Union, List, Dict, Any
import copy
from ..hub import Template

class MemoryManager:
    def __init__(self, memory: List[Union[str, "Template", Dict[str, Any]]] = None, k: int = 10):
        self.input_memory = memory or []
        self.memory = []
        self.locked_items = None
        self.remember_rounds = k

    def confirm_memory_init(self):
        if not self.memory and self.input_memory:
            for x in self.convert_prompt_to_messages(self.input_memory):
                self.memory.append(x)
        return self.memory

    def convert_prompt_to_messages(self, prompt: Union[str, List[Union[str, dict, Template]]]):
        if isinstance(prompt, str):
            return [{'role': 'system', 'content': prompt}]
        if isinstance(prompt, Template):
            return [{'role': 'system', 'content': prompt.get_prompt()}]
        if isinstance(prompt, list) and len(prompt) == 1 and isinstance(prompt[0], str):
            return [{'role': 'system', 'content': prompt[0]}]

        messages = []
        roles = ['user', 'assistant']
        for i, element in enumerate(prompt):
            if i > 0 and messages[0].get('role') == 'system':
                _i = i + 1
            else:
                _i = i
            if isinstance(element, dict):
                messages.append(element)
            elif isinstance(element, str):
                messages.append({'role': roles[_i % 2], 'content': element})
            elif isinstance(element, Template):
                element.desk = self.desk
                role = 'system' if _i == 0 else roles[_i % 2]
                messages.append({'role': role, 'content': element.get_prompt()})
        return messages

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if prompt:
            if isinstance(prompt, str):
                new_memory = [{"role": "user", "content": prompt}]
            else:
                new_memory = prompt
            self.memory.extend(new_memory)
        else:
            new_memory = []
        return new_memory

    def remember_response(self, response: Union[str, List[dict]]):
        if response:
            if isinstance(response, str):
                new_memory = [{"role": "assistant", "content": response}]
            else:
                new_memory = response
            self.memory.extend(new_memory)
        else:
            new_memory = []
        return new_memory

    def get_chat_memory(self, remember_rounds: int = None):
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_memory = self.memory[:self.locked_items]
            new_memory += self.memory[self.locked_items:][-final_k:]
        else:
            new_memory = self.memory[-final_k:]
        # 调用 Runnable 类中的 append_knowledge_to_messages 方法
        self.append_knowledge_to_messages(new_memory)
        return new_memory

    @property
    def output(self):
        return self.memory[-1]['content'] if self.memory else ""