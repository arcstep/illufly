import json

from abc import abstractmethod
from typing import Union, List, Dict, Any

from ...utils import merge_blocks_by_index
from ...io import TextBlock, create_chk_block

from .base import Runnable
from .state import State
from .history import History


class ChatAgent(Runnable):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。
    基于对话智能体可以实现多智能体协作。

    **对话智能体只有一个 call 方法，用于生成对话内容**

    该方法在不同参数配置下，可以实现不同的对话功能。
    - :prompt: 提供 prompt 时，表示这是一个基本的对话功能。
    - :tools: 增加 tools 参数，将有大模型决定是否使用工具回调，并给出工具提示。
    - :toolkits: 增加 toolkits 参数，将不仅给出工具提示，还将进一步执行工具。
    - :template: 增加 template 参数，将使用指定的模板来生成对话内容，并且每次执行时会清空对话内容。

    **多智能体协作：核心概念是行为，可通过 action 参数指定行为。**

    每个智能体有一组基本相同的行为能力。
    1. 默认的行为是对话
    2. 增加 template 参数后的行为是协作（清空对话重来）
    3. 行为还包括扩写、评估等。
    """

    def __init__(self, memory: List[Dict[str, Any]]=None, k: int=10, threads_group: str=None, tools=None, toolkits=None, **kwargs):
        """
        :param memory: 初始化记忆。
        :param k: 记忆轮数。
        :param threads_group: 线程组名称。

        可以在环境变量中配置默认的线程池数量。
        例如：
        DEFAULT_MAX_WORKERS_CHAT_OPENAI=10
        可以配置CHAT_OPENAI线程池的最大线程数为10。

        self.locked_items 是锁定的记忆条数，每次对话时将会保留。
        """
        super().__init__(threads_group or "CHAT_AGENT")
        self.tools = tools or []
        self.toolkits = toolkits or []
        self.memory = memory or []
        self.locked_items = None
        self.remember_rounds = k
        self.state = State()
    
    @property
    def output(self):
        return self.memory[-1]['content'] if self.memory else ""

    def create_new_memory(self, prompt: Union[str, List[dict]]):
        if isinstance(prompt, str):
            new_memory = {"role": "user", "content": prompt}
        else:
            new_memory = prompt[-1]
        self.memory.append(new_memory)
        return [new_memory]

    def remember_response(self, response: Union[str, List[dict]]):
        if isinstance(response, str):
            new_memory = [{"role": "assistant", "content": response}]
        else:
            new_memory = response
        self.memory.extend(new_memory)
        return new_memory

    def get_chat_memory(self, remember_rounds:int=None):
        """
        优化聊天记忆。

        1. 如果记忆中包含系统消息，则只保留前 locked_items 条消息。
        2. 否则，只保留最后 k 轮对话消息。
        3. 如果有准备好的知识，则将知识追加到消息列表中。
        4. TODO: 移除工具回调等过程细节消息。
        5. TODO: 将对话历史制作成对应摘要，以提升对话质量。
        6. TODO: 根据问题做「向量检索」，提升对话的理解能力。
        7. TODO: 根据问题做「概念检索」，提升对话的理解能力。

        """
        _k = self.remember_rounds if remember_rounds is None else remember_rounds
        final_k = 2 * _k if _k >= 1 else 1
        if len(self.memory) > 0 and self.memory[0]['role'] == 'system':
            new_memory = self.memory[:self.locked_items]
            new_memory += self.memory[self.locked_items:][-final_k:]
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
        toolkits = kwargs.get("toolkits", self.toolkits)
        if toolkits:
            resp = self.tools_calling(prompt, *args, **kwargs)
        else:
            resp = self.chat(prompt, *args, **kwargs)

        for block in resp:
            yield block

    def chat(self, prompt: Union[str, List[dict]], *args, **kwargs):
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

    def tools_calling(self, prompt: Union[str, List[dict]], *args, **kwargs):
        toolkits = kwargs.pop("toolkits", self.toolkits)

        new_memory = self.get_chat_memory()
        new_memory.extend(self.create_new_memory(prompt))

        to_continue_call_llm = True
        while(to_continue_call_llm):
            to_continue_call_llm = False
            output_text = ""
            tools_call = []

            # 大模型推理
            for block in self.generate(new_memory, *args, **kwargs):
                yield block
                if block.block_type == "chunk":
                    output_text += block.content
                if block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            # 合并工具回调
            final_tools_call = merge_blocks_by_index(tools_call)            
            if final_tools_call:
                yield TextBlock("tools_call_final", json.dumps(final_tools_call, ensure_ascii=False))
                # 如果大模型的结果返回多个工具回调，则要逐个调用完成才能继续下一轮大模型的问调用。
                for index, tool in final_tools_call.items():

                    for struct_tool in toolkits:
                        if tool['function']['name'] == struct_tool.name:
                            args = json.loads(tool['function']['arguments'])
                            tool_resp = ""

                            tool_func_result = struct_tool.func(**args)
                            for x in tool_func_result:
                                if isinstance(x, TextBlock):
                                    if x.block_type == "tool_resp_final":
                                        tool_resp = x.text
                                    yield x
                                else:
                                    tool_resp += x
                                    yield TextBlock("tool_resp_chunk", x)
                            tool_resp_message = [
                                {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [tool]
                                },
                                {
                                    "tool_call_id": tool['id'],
                                    "role": "tool",
                                    "name": tool['function']['name'],
                                    "content": tool_resp
                                }
                            ]
                            new_memory.extend(tool_resp_message)
                            self.remember_response(tool_resp_message)
                            to_continue_call_llm = True
            else:
                self.remember_response(output_text)
                # 补充校验的尾缀
                yield create_chk_block(output_text)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        pass