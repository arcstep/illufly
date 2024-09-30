from typing import Union, List, Dict, Any
import copy
from ..template import Template
from ....hub import get_template_variables
from .message import Messages, Message

class MemoryManager:
    def __init__(self, style: str=None, memory: Union[List[Union[str, "Template", Dict[str, Any]]], Messages]=None, input_vars: List[str]=None, remember_rounds: int=None, **kwargs):
        self.style = style
        self.memory = []
        self.bound_vars = set() # 被消息列表中的 Template 绑定的变量清单
        self.init_messages = Messages(memory, style=self.style, input_vars=input_vars)
        self.locked_items = self.init_messages.length
        self.remember_rounds = remember_rounds if remember_rounds is not None else 10

        for template in self.init_messages.all_templates:
            template.bind_runnables(self)
            self.bound_vars.update(get_template_variables(template.template_text))

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        """
        创建新的记忆。
        """
        if prompt:
            if isinstance(prompt, str):
                new_memory = Messages([("user", prompt)], style=self.style)
            else:
                new_memory = Messages(prompt, style=self.style)

            self.memory.extend(new_memory.to_list())
            return new_memory.to_list()
        else:
            return []

    def remember_response(self, response: Union[str, List[dict]]):
        """
        将回答添加到记忆中。
        """
        if response:
            if isinstance(response, str):
                new_memory = Messages([("assistant", response)], style=self.style).to_list()
            else:
                new_memory = response

            self.memory.extend(new_memory)
            return new_memory
        else:
            return []

    def get_chat_memory(self, remember_rounds: int = None, knowledge: List[str] = None):
        """
        获取短时记忆。

        主要用于构建对话时的历史记忆，并将其作为提示语中上下文的一部分。

        优化策略：
        - 已根据 rember_rounds 可以指定记忆的轮数，以避免对话历史过长
        - 已根据 locked_items 可以锁定对话开始开始必须保留的上下文，例如，写作场景中可以锁定最初写作提纲
        - 已根据 knowledge 可以补充遗漏的背景知识，并避免重复添加
        - ...
        - 还可以: 使用向量库，从知识库服务器检索强相关的内容
        - 还可以: 使用向量库，查询强相关的历史记忆
        - 还可以: 使用相似性比较，仅补充与问题相关的记忆
        - 还可以: 剔除工具调用过程细节、对长对话做摘要等
        """
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_messages = self.memory[:self.locked_items]
            new_messages += self.memory[self.locked_items:][-final_k:]
        else:
            new_messages = self.memory[-final_k:]
        # 调用 BaseAgent 类中的 append_knowledge_to_messages 方法
        final_memory = self._append_knowledge_to_messages(new_messages, knowledge)
        return final_memory.to_list()

    def _append_knowledge_to_messages(self, new_messages: List[Any], knowledge: List[str]):
        """
        构造短期记忆时，将知识库中的内容添加到消息列表中。
        """
        new_memory = Messages(new_messages, style=self.style)
        if not knowledge:
            return new_memory

        existing_contents = {msg['content'] for msg in new_messages if msg['role'] == 'user'}
        for kg in knowledge:
            content = f'已知知识：\n{kg}'
            if content not in existing_contents:
                new_memory.extend([
                    ("user", content),
                    ("assistant", 'OK')
                ])
        return new_memory
