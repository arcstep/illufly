import json

from abc import abstractmethod
from typing import Union, List, Dict, Any

from ...utils import merge_blocks_by_index
from ...io import TextBlock

from .base import CallBase
from .state import State
from .history import History


class ChatAgent(CallBase):
    def __init__(self, memory: List[Dict[str, Any]]=None, k: int=10, threads_group: str=None):
        self.memory = memory or []
        self.locked_k = 1
        self.remember_k = k
        self.state = State()
        super().__init__(threads_group or "base_llm")

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if isinstance(prompt, str):
            new_memory = {"role": "user", "content": prompt}
        else:
            new_memory = prompt[-1]
        self.memory.append(new_memory)
        return [new_memory]

    def remember_response(self, response: Union[str, List[dict]]):
        if isinstance(response, str):
            new_memory = {"role": "assistant", "content": response}
        else:
            new_memory = response[-1]
        self.memory.append(new_memory)

    def get_chat_memory(self, remember_k:int=None):
        """
        优化聊天记忆。

        1. 如果记忆中包含系统消息，则只保留前 locked_k 条消息。
        2. 否则，只保留最后 k 轮对话消息。
        3. 如果有准备好的知识，则将知识追加到消息列表中。
        4. TODO: 移除工具回调等过程细节消息。
        5. TODO: 将对话历史制作成对应摘要，以提升对话质量。
        6. TODO: 根据问题做「向量检索」，提升对话的理解能力。
        7. TODO: 根据问题做「概念检索」，提升对话的理解能力。

        """
        _k = self.remember_k if remember_k is None else remember_k

        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_memory = self.memory[:self.state.locked_k]
            new_memory += self.memory[self.state.locked_k:][-final_k:]
        else:
            new_memory = self.memory[-final_k:]

        self.add_knowledge(new_memory)

        return new_memory

    def add_knowledge(self, new_memory: List[Any]):
        """
        将知识库中的知识追加到消息列表中。
        """
        existing_contents = {msg['content'] for msg in new_memory if msg['role'] == 'user'}
        
        for kg in self.state.get_knowledge():
            content = f'已知：{kg}'
            if content not in existing_contents:
                new_memory.extend([{
                    'role': 'user',
                    'content': content
                },
                {
                    'role': 'assistant',
                    'content': 'OK, 我将利用这个知识回答后面问题。'
                }])
        return new_memory


    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        new_memory = self.get_chat_memory()
        new_memory.extend(self.create_new_memory(prompt))

        output_text = ""
        tools_call = []
        for block in self.generate(new_memory, *args, **kwargs):
            yield block
            if block.block_type == "chunk":
                output_text += block.content
            if block.block_type == "tools_call_chunk":
                tools_call.append(json.loads(block.text))

        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            content = json.dumps(final_tools_call, ensure_ascii=False)
            self.remember_response(content)
            yield TextBlock("tools_call_final", content)
        else:
            if output_text:
                self.remember_response(output_text)
                yield TextBlock("text_final", output_text)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        pass