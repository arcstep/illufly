from typing import Union, List, Dict, Any, Callable
from ....hub import get_template_variables
from ..template import Template
from ..binding_manager import BindingManager
from .message import Messages, Message

class MemoryManager(BindingManager):
    def __init__(
        self,
        style: str=None,
        memory: Union[List[Union[str, "Template", Dict[str, Any]]], Messages]=None,
        remember_rounds: int=None,
        template_binding: Dict[str, Any]=None,
        **kwargs
    ):
        if template_binding is None:
            template_binding = {}

        if not isinstance(template_binding, Dict):
            raise ValueError("template_binding must be a dictionary")

        super().__init__(**kwargs)

        self.style = style
        self.memory = []
        self.remember_rounds = remember_rounds if remember_rounds is not None else 10

        self.init_messages = Messages(memory, style=self.style)
        self.locked_items = self.init_messages.length
        for template in self.init_messages.all_templates:
            self.bind_consumers(template, template_binding)

    def get_bound_vars(self, messages: Messages):
        """
        获取消息列表中所有 Template 的绑定变量。
        """
        bound_vars = set()
        for template in messages.all_templates:
            template.bind_providers((self, self.template_binding))
            bound_vars.update(template.consumer_dict)
            mapping_index = [v for k, v in self.template_binding.items() if k and not isinstance(v, Callable)]
            bound_vars.update(set(mapping_index))
        return bound_vars

    def get_chat_memory(self, prompt: Union[str, List[dict]], new_chat: bool=False, remember_rounds: int = None, knowledge: List[str] = None):
        """
        获取对话所需的短时记忆。

        主要用于构建对话时的历史记忆，并将其作为提示语中上下文的一部分。
        具体包括：
        - 根据问题场景，确定是否建立新一轮对话
        - 根据记忆，捕捉已有对话记录
        - 根据所提供的知识背景，构造知识背景对话
        - 根据问题，构造提问对话
        - 将以上对话合并，构造完整的对话场景短时记忆

        优化策略：
        - 根据 rember_rounds 可以指定记忆的轮数，以避免对话历史过长
        - 根据 locked_items 可以锁定对话开始开始必须保留的上下文，例如，写作场景中可以锁定最初写作提纲
        - 根据 knowledge 可以补充遗漏的背景知识，并避免重复添加
        """

        # 构建 prompt 标准形式
        if isinstance(prompt, str):
            prompt = [{"role": "user", "content": prompt}]
        new_prompt = prompt if isinstance(prompt, Messages) else Messages(prompt, style=self.style)

        # 确定是否新一轮对话
        if new_chat or new_prompt.has_role("system") or not self.memory:
            self.memory.clear()
            new_chat = True

        # 整理出友好的提示语消息列表
        new_messages = self.build_new_messages(new_prompt, new_chat)

        # 调用 BaseAgent 类中的 append_knowledge_to_messages 方法
        kg_memory = self.get_knowledge_memory(new_messages, knowledge)
        history_memory = self.get_history_memory(new_chat, remember_rounds)

        if new_messages.has_role("system"):
            new_messages = new_messages[:1] + kg_memory + history_memory + new_messages[1:]
            self.memory = new_messages.to_list()
            return self.memory
        else:
            self.memory = (kg_memory + new_messages).to_list()
            return (kg_memory + history_memory + new_messages).to_list()

    def get_history_memory(self, new_chat: bool=False, remember_rounds: int = None):
        """
        获取历史记忆。
        """
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_messages = self.memory[:self.locked_items]
            new_messages += self.memory[self.locked_items:][-final_k:]
        else:
            new_messages = self.memory[-final_k:]
        return Messages(new_messages, style=self.style)

    def build_new_messages(self, new_messages: Messages, new_chat: bool=False, **kwargs):
        """
        构建提问消息列表。
        """

        if new_messages.has_role("system"):
            # 如果新消息列表中包含 system 角色，已经提前清理了 memory 并设置 new_chat 为 True
            # 现在需要绑定模板变量
            templates = new_messages.all_templates
            for template in templates:
                self.bind_consumers(template, binding_map={**kwargs.get("template_binding", {}), **self.template_binding})
        elif new_chat and self.init_messages.length > 0:
            # 如果是新对话，且需要启用 init_messages 模板，则将其与 new_messages 合并
            new_messages = self.init_messages + new_messages

        if 'task' in self.get_bound_vars(new_messages) and new_messages[-1].role == 'user':
            # 如果 task 变量被模板使用，则将尾部消息列表中的 user 角色消息取出，并赋值给 task 变量用于绑定映射
            self._task = new_messages.messages.pop(-1).content

        if new_messages[-1].role == 'system':
            # 如果新消息列表的尾部是 system 消息，则需要补充一个 user 角色消息
            new_messages.append({"role": "user", "content": "请开始"})

        return new_messages

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

    def get_knowledge_memory(self, chat_messages: Messages, knowledge: List[str]):
        """
        构造短期记忆时，将知识库中的内容添加到消息列表中。
        """
        if not knowledge:
            return Messages([], style=self.style)

        existing_contents = {msg.content for msg in chat_messages if msg.role == 'user'}
        kg_content = ''
        for kg in knowledge:
            content = f'已知知识：\n{kg}'
            if content not in existing_contents:
                kg_content += content

        kg_memory = Messages(
            [("user", kg_content), ("assistant", "OK")],
            style=self.style
        )

        return kg_memory
