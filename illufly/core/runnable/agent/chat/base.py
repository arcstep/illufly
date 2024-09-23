import json
import copy

from abc import abstractmethod
from typing import Union, List, Dict, Any

from .....utils import merge_blocks_by_index, extract_text
from .....io import TextBlock, EndBlock

from ..base import BaseAgent
from .memory_manager import MemoryManager
from .message import Messages, Message
from .knowledge_manager import KnowledgeManager
from .tools_manager import ToolsManager

class ChatAgent(BaseAgent, KnowledgeManager, MemoryManager, ToolsManager):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。
    """

    def __init__(
        self,
        end_chk: bool = False,
        start_marker: str=None,
        end_marker: str=None,
        **kwargs
    ):
        """
        对话智能体支持的核心能力包括：
        - tools：工具调用
        - memory：记忆管理
        - knowledge：知识管理
        """
        BaseAgent.__init__(self, **kwargs)
        MemoryManager.__init__(self, **kwargs)
        KnowledgeManager.__init__(self, **kwargs)
        ToolsManager.__init__(self, **kwargs)

        self.end_chk = end_chk

        self.start_marker = start_marker or "```"
        self.end_marker = end_marker or "```"

        # 在子类中应当将模型参数保存到这个属性中，以便持久化管理
        self.model_args = {}
        self.default_call_args = {}

        # 增加的可绑定变量
        self.task = ""

    @property
    def last_output(self):
        return self.memory[-1]['content'] if self.memory else ""

    @property
    def exported_vars(self):
        return {
            **super().exported_vars,
            "task": self.task
        }

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        if not isinstance(prompt, str) and not isinstance(prompt, list):
            raise ValueError("prompt 必须是字符串或消息列表")

        # 如果重新构造 system 角色的消息，一般不使用模板构建
        is_prompt_using_system_role = False
        if isinstance(prompt, List) and prompt[0].get("role", "") == "system":
            new_chat = True
            is_prompt_using_system_role = True

        # 确认是否切换新的对话轮次
        # 条件1：new_chat=True
        # 条件2：提供的提示语内容使用 system 角色
        new_chat = kwargs.pop("new_chat", False) or not self.memory
        new_task_flag = False

        if new_chat:
            # TODO: 应当在清空前做好历史管理
            self.memory.clear()
            new_task_flag = True

            ## 补充初始记忆
            if not is_prompt_using_system_role and self.init_messages.length > 0:
                # 如果需要在模板中使用了 task 变量，就将 prompt 赋值给 task，并将 prompt 设置为空
                # 在接下来使用 init_messagess.to_list 构建历史记忆时，会通过绑定变量使用到 task 变量
                # 进而作为历史记忆的一部份传递给模型做推理计算
                if "task" in self.bound_vars:
                    if isinstance(prompt, str):
                        self.task = prompt
                    else:
                        messages = Messages(prompt)
                        self.task = messages.last_content()
                    prompt = []

                is_prompt_using_system_role = True
                self.memory = self.init_messages.to_list()

        resp = self.chat_with_tools_calling(prompt, *args, **kwargs)

        for block in resp:
            yield block

        # 补充校验的尾缀
        if self.end_chk:
            yield EndBlock(self.last_output)
        
        # 重新锁定当前记忆中的条数，包括刚刚获得的回答
        # 避免在提取短期记忆时被遗弃
        if is_prompt_using_system_role:
            self.locked_items = len(self.memory)

    def chat_with_tools_calling(self, prompt: Union[str, List[dict]], *args, **kwargs):

        messages = self.get_chat_memory(knowledge=self.get_knowledge())
        messages.extend(self.create_new_memory(prompt))

        to_continue_call_llm = True
        while(to_continue_call_llm):
            to_continue_call_llm = False
            output_text = ""
            tools_call = []

            # 大模型推理
            for block in self.generate(messages, *args, **kwargs):
                yield block
                if block.block_type == "chunk":
                    output_text += block.content
                elif block.block_type == "text_final":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))
            
            final_tools_call = merge_blocks_by_index(tools_call)
            if final_tools_call:
                # 记录工具回调提示
                final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
                yield TextBlock("tools_call_final", final_tools_call_text)

            # 合并工具回调
                for index, tool in final_tools_call.items():
                    # 如果大模型的结果返回多个工具回调，则要逐个调用完成才能继续下一轮大模型的问调用。
                    # 追加工具提示部份到记忆
                    tools_call_message = [
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [tool]
                        }
                    ]
                    messages.extend(tools_call_message)
                    self.remember_response(tools_call_message)

                    if self.exec_tool:
                        # 执行工具回调
                        tools_list = kwargs.get("tools", self.tools)
                        for struct_tool in tools_list:
                            if tool['function']['name'] == struct_tool.name:
                                tool_args = json.loads(tool['function']['arguments'])
                                tool_resp = ""

                                tool_func_result = struct_tool.func(**tool_args)
                                for x in tool_func_result:
                                    if isinstance(x, TextBlock):
                                        if x.block_type == "tool_resp_final":
                                            tool_resp = x.text
                                        elif x.block_type == "chunk":
                                            tool_resp += x.text
                                        yield x
                                    else:
                                        tool_resp += x
                                        yield TextBlock("tool_resp_chunk", x)

                                # 追加工具返回消息部份到记忆
                                tool_resp_message = [
                                    {
                                        "tool_call_id": tool['id'],
                                        "role": "tool",
                                        "name": tool['function']['name'],
                                        "content": tool_resp
                                    }
                                ]
                                messages.extend(tool_resp_message)
                                self.remember_response(tool_resp_message)
                                to_continue_call_llm = True
            else:
                # 当前并没有需要回调的工具，直接记录大模型的输出
                final_output_text = extract_text(output_text, self.start_marker, self.end_marker)
                self.remember_response(final_output_text)
                yield TextBlock("text_final", final_output_text)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        raise NotImplementedError("子类必须实现 generate 方法")
