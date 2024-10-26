import os
import time
import json
import random

from typing import Union, List, Dict, Any, Callable
from .....utils import filter_kwargs, raise_invalid_params, get_env
from .....hub import get_template_variables
from ...message import Messages, Message
from ...prompt_template import PromptTemplate
from ...binding_manager import BindingManager

class ThreadIDGenerator:
    def __init__(self, counter: int=0):
        self.counter = counter

    def create_id(self):
        while True:
            timestamp = str(int(time.time()))[-6:]
            random_number = f'{random.randint(0, 9999):04}'
            counter_str = f'{self.counter:04}'
            yield f'{timestamp}-{random_number}-{counter_str}'
            self.counter = 0 if self.counter == 9999 else self.counter + 1

class MemoryManager(BindingManager):
    @classmethod
    def get_history_dir(cls, agent_name: str="default"):
        return os.path.join(get_env("ILLUFLY_HISTORY"), cls.__name__.upper(), agent_name)

    @classmethod
    def get_history_file_path(cls, thread_id: str, agent_name: str="default"):
        if thread_id:
            return os.path.join(
                cls.get_history_dir(agent_name),
                f"{thread_id}.json"
            )
        else:
            raise ValueError("thread_id MUST not be None")

    @classmethod
    def list_memory_threads(cls, agent_name: str="default"):
        memory_dir = cls.get_history_dir(agent_name)
        if not os.path.exists(memory_dir):
            return []
        file_list = [os.path.basename(file) for file in os.listdir(memory_dir) if file.endswith(".json") and not file.startswith(".")]
        thread_ids = [file.replace(".json", "") for file in file_list]

        def thread_id_key(thread_id):
            ids = thread_id.split("-")
            return f'{ids[0]}-{ids[-1]}'

        return sorted(thread_ids, key=thread_id_key)

    @classmethod
    def get_current_thread_rounds(cls):
        all_thread_ids = cls.list_memory_threads()
        if all_thread_ids:
            ids = all_thread_ids[-1].split("-")
            return int(ids[-1]) + 1
        else:
            return 0

    @classmethod
    def initialize_thread_id_generator(cls):
        cls.thread_id_generator = ThreadIDGenerator(cls.get_current_thread_rounds())
        cls.thread_id_gen = cls.thread_id_generator.create_id()

    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "style": "消息样式",
            "memory": "记忆列表",
            "remember_rounds": "记忆轮数",
            **BindingManager.allowed_params(),
        }

    def __init_subclass__(cls, **kwargs):
        """
        在子类初始化时，调用初始化方法。

        为每个子类构造独立的 thread_id 生成器，但在其实例中可以共享。
        """
        super().__init_subclass__(**kwargs)
        cls.initialize_thread_id_generator()

    def __init__(
        self,
        style: str=None,
        memory: Union[List[Union[str, "PromptTemplate", Dict[str, Any]]], Messages]=None,
        remember_rounds: int=None,
        **kwargs
    ):
        raise_invalid_params(kwargs, self.allowed_params())
        super().__init__(**filter_kwargs(kwargs, BindingManager.allowed_params()))

        self.style = style
        self.memory = []
        self.remember_rounds = remember_rounds if remember_rounds is not None else 10

        self.init_memory = []
        self.reset_init_memory(memory)
        self._thread_id = None

    @property
    def thread_id(self):
        return self._thread_id

    def create_new_thread(self):
        """
        开启新一轮对话
        """
        self.memory.clear()
        self._thread_id = next(self.__class__.thread_id_gen)

    def reset_init_memory(self, messages: Union[str, List[dict]]):
        self.init_memory = Messages(messages, style=self.style)
        for template in self.init_memory.all_templates:
            self.bind_consumer(template)

    def get_bound_vars(self, new_messages: Messages, new_chat: bool=False):
        """
        获取所有被 PromptTemplates 绑定的变量。

        这主要用于判断 provider_dict 中的键值是否被消息列表中的模板绑定使用。
        典型的场景包括：判断 input 和 tools_desc 是否被使用，这将会影响对话过程中组织对话或提供 tools 参数给大模型。
        """
        _new_messages = self.init_memory
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
    # 保存记忆
    def save_memory(self):
        path = self.get_history_file_path(self.thread_id, self.name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False)

    @property
    def thread_ids(self):
        return self.list_memory_threads(self.name)

    # 加载记忆
    def load_memory(self, thread_id: Union[str, int]=None):
        """
        加载记忆。

        如果 thread_id 是字符串，则直接加载指定线程的记忆；
        如果 thread_id 是整数，则将其当作索引，例如 thread_id=-1 表示加载最近一轮对话的记忆。
        """
        path = None
        if isinstance(thread_id, str):
            self._thread_id = thread_id
            path = self.get_history_file_path(thread_id, self.name)
        elif isinstance(thread_id, int):
            if self.thread_ids:
                self._thread_id = self.thread_ids[thread_id]
                path = self.get_history_file_path(self.thread_ids[thread_id], self.name)

        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.memory = json.load(f)

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
        new_prompt = prompt if isinstance(prompt, Messages) else Messages(prompt, style=self.style)

        # 确定是否新一轮对话
        if new_chat or new_prompt.has_role("system") or not self.memory:
            new_chat = True
            self.create_new_thread()

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

        # 无论新消息列表中是否包含 system 角色，都需要绑定模板变量，但应当是��态绑定
        templates = new_messages.all_templates
        for template in templates:
            self.bind_consumer(template, dynamic=True)

        if new_chat:
            if not new_messages.has_role("system"):
                # 只要没有提供 system 角色，就启用 init_memory 模板
                # 合并 new_messages 和 init_memory
                new_messages = self.init_memory + new_messages

            # 如果在合并后的 new_messages 中，task 变量被模板使用，
            # 则将尾部消息列表中的 user 角色消息取出，并赋值给 task 变量用于绑定映射
            bound_vars = self.get_bound_vars(new_messages, new_chat=new_chat)
            if 'task' in bound_vars and new_messages[-1].role == 'user':
                new_messages.messages.pop(-1)
            
            # 如果新消息列表的尾部是 system 消息，则需要补充一个 user 角色消息
            # 否则，缺少用户消息会让大模型拒绝回答任何问题
            if new_messages[-1].role == 'system':
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
