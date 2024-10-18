from typing import Union, List, Dict, Any, Callable
from .....utils import filter_kwargs, raise_invalid_params
from .....hub import get_template_variables
from ...message import Messages, Message
from ...prompt_template import PromptTemplate
from ...binding_manager import BindingManager

class MemoryManager(BindingManager):
    @classmethod
    def available_init_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "style": "消息样式",
            "memory": "记忆列表",
            "remember_rounds": "记忆轮数",
            **BindingManager.available_init_params(),
        }

    def __init__(
        self,
        style: str=None,
        memory: Union[List[Union[str, "PromptTemplate", Dict[str, Any]]], Messages]=None,
        remember_rounds: int=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.available_init_params())
        super().__init__(**filter_kwargs(kwargs, BindingManager.available_init_params()))

        self.style = style
        self.memory = []
        self.remember_rounds = remember_rounds if remember_rounds is not None else 10

        self.init_messages = Messages(memory, style=self.style)
        for template in self.init_messages.all_templates:
            self.bind_consumer(template)

    def get_bound_vars(self, new_messages: Messages, new_chat: bool=False):
        """
        获取所有被 PromptTemplates 绑定的变量。

        这主要用于判断 provider_dict 中的键值是否被消息列表中的模板绑定使用。
        典型的场景包括：判断 input 和 tools_desc 是否被使用，这将会影响对话过程中组织对话或提供 tools 参数给大模型。
        """
        _new_messages = self.init_messages
        if new_chat and new_messages.has_role("system"):
            _new_messages = new_messages
        else:
            _new_messages += new_messages

        bound_vars = set()
        for template in _new_messages.all_templates:
            _template = template.selected
            _template_vars = _template.template_vars
            bound_vars.update(_template_vars)
            for provider_key, consumer_key in _template.lazy_binding_map.items():
                if provider_key in _template_vars:
                    bound_vars.remove(provider_key)
                    if consumer_key in self.provider_dict:
                        bound_vars.add(consumer_key)
        return bound_vars

    def build_chat_memory(self, prompt: Union[str, List[dict]], new_chat: bool=False, remember_rounds: int = None):
        """
        获取对话所需的短时记忆。

        主要用于构建对话时的历史记忆，并将其作为提示语中上下文的一部分。
        具体包括：
        - 根据问题场景，确定是否建立新一轮对话
        - 根据问题，构造提问对话，并补充模板变量
        - 根据记忆，捕捉已有对话记录
        - 根据所提供的知识背景，构造知识背景对话
        - 将以上对话合并，构造完整的对话场景短时记忆
        """

        # 构建 prompt 标准形式
        if isinstance(prompt, str):
            prompt = [{"role": "user", "content": prompt}]
        new_prompt = prompt if isinstance(prompt, Messages) else Messages(prompt, style=self.style)

        # 确定是否新一轮对话
        if new_chat or new_prompt.has_role("system") or not self.memory:
            self.memory.clear()
            new_chat = True

        new_messages = self.build_new_messages(new_prompt, new_chat)
        history_memory = self.get_history_memory(new_chat, remember_rounds)

        if new_messages.has_role("system"):
            new_messages_list = Messages((new_messages[:1] + history_memory.messages + new_messages[1:]), style=self.style).to_list()
            self.memory.extend(new_messages_list)
            return new_messages_list
        else:
            self.memory.extend(new_messages.to_list())
            return (history_memory + new_messages).to_list()

    def get_history_memory(self, new_chat: bool=False, remember_rounds: int = None):
        """
        获取历史记忆。
        """
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_messages = self.memory[:1]
            new_messages += self.memory[1:][-final_k:]
        else:
            new_messages = self.memory[-final_k:]
        return Messages(new_messages, style=self.style)

    def build_new_messages(self, prompt: Union[str, List[dict]], new_chat: bool=False, **kwargs):
        """
        构建提问消息列表。
        """
        # 构建 prompt 标准形式
        if isinstance(prompt, str):
            prompt = [{"role": "user", "content": prompt}]
        new_messages = prompt if isinstance(prompt, Messages) else Messages(prompt, style=self.style)

        # 无论新消息列表中是否包含 system 角色，都需要绑定模板变量，但应当是动态绑定
        templates = new_messages.all_templates
        for template in templates:
            self.bind_consumer(template, dynamic=True)

        # 如果是新对话，只要没有提供 system 角色，就启用 init_messages 模板
        # 合并 new_messages 和 init_messages
        if new_chat and not new_messages.has_role("system"):
            new_messages = self.init_messages + new_messages

        # 如果在合并后的 new_messages 中，task 变量被模板使用
        #   则将尾部消息列表中的 user 角色消息取出，并赋值给 task 变量用于绑定映射
        if 'task' in self.get_bound_vars(new_messages, new_chat=new_chat) and new_messages[-1].role == 'user':
            new_messages.messages.pop(-1)

        if new_messages and new_messages[-1].role == 'system':
            # 如果新消息列表的尾部是 system 消息，则需要补充一个 user 角色消息
            # 否则，缺少用户消息会让大模型拒绝回答任何问题
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

