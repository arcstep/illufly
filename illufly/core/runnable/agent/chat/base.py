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
        self.model_args = {"base_url": None, "api_key": None}
        self.default_call_args = {"model": None}

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

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        raise NotImplementedError("子类必须实现 generate 方法")

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
                # 在接下来使用 init_messagess.to_list 构建记忆表，会通过绑定变量使用到 task 变量
                # 进而作为记忆表的一部份传递给模型做推理计算
                if "task" in self.bound_vars:
                    if isinstance(prompt, str):
                        self.task = prompt
                    else:
                        messages = Messages(prompt)
                        self.task = messages.last_content()
                    prompt = []

                is_prompt_using_system_role = True
                self.memory = self.init_messages.to_list()

        yield from self.chat_with_tools_calling(prompt, *args, **kwargs)

        # 补充校验的尾缀
        if self.end_chk:
            yield EndBlock(self.last_output)
        
        # 重新锁定当前记忆中的条数，包括刚刚获得的回答
        # 避免在提取短期记忆时被遗弃
        if is_prompt_using_system_role:
            self.locked_items = len(self.memory)

    def chat_with_tools_calling(self, prompt: Union[str, List[dict]], *args, **kwargs):
        chat_memory = self.get_chat_memory(knowledge=self.get_knowledge())
        chat_memory.extend(self.create_new_memory(prompt))

        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False
            output_text, tools_call = "", []

            for block in self.generate(chat_memory, *args, **kwargs):
                yield block
                if block.block_type == "chunk":
                    output_text += block.content
                elif block.block_type == "text_final":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            final_tools_call = merge_blocks_by_index(tools_call)
            if final_tools_call:
                for block in self.handle_tools_call(final_tools_call, chat_memory, kwargs):
                    if isinstance(block, TextBlock) and block.block_type == "tool_resp_final":
                        to_continue_call_llm = True
                    yield block
            else:
                final_output_text = extract_text(output_text, self.start_marker, self.end_marker)
                chat_memory.append({
                    "role": "assistant",
                    "content": final_output_text
                })
                self.remember_response(final_output_text)
                yield TextBlock("text_final", final_output_text)

                # 检查 final_output_text 的文本结果中是否包含 <tool_call> 结构
                # 示例如下：
                # <tool_call>
                # {"name": "get_current_weather", "arguments": {"location": "Paris", "unit": "celsius"}}
                # </tool_call>
                #
                # 如果包含，仍然需要执行工具调用
                # 这主要是为了兼容 Ollama 等兼容 openai 接口协议的情况
                # 但其工具回调返回的是 <tool_call> 结构，而非 openai 协议现有的结构
                tool_call_start = final_output_text.find("<tool_call>")
                tool_call_end = final_output_text.find("</tool_call>")
                if tool_call_start != -1 and tool_call_end != -1:
                    tool_call_json = final_output_text[tool_call_start + len("<tool_call>"):tool_call_end]
                    tool_call_func = json.loads(tool_call_json)
                    try:
                        tool_call = {
                            "function": {
                                "name": tool_call_func.get("name"),
                                "arguments": json.dumps(tool_call_func.get("arguments", "[]"), ensure_ascii=False)
                            }
                        }
                        for block in self.handle_embedded_tool_call(tool_call, chat_memory, kwargs):
                            if isinstance(block, TextBlock) and block.block_type == "tool_resp_final":
                                to_continue_call_llm = True
                            yield block
                        # to_continue_call_llm = True
                    except json.JSONDecodeError:
                        pass

    def handle_tools_call(self, final_tools_call, chat_memory, kwargs):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield TextBlock("tools_call_final", final_tools_call_text)

        for index, tool in final_tools_call.items():
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]
            chat_memory.extend(tools_call_message)
            self.remember_response(tools_call_message)

            if self.exec_tool:
                for block in self.execute_tool(tool, chat_memory, kwargs):
                    if isinstance(block, TextBlock) and block.block_type == "tool_resp_final":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        chat_memory.extend(tool_resp_message)
                        self.remember_response(tool_resp_message)
                    yield block

    def execute_tool(self, tool, chat_memory, kwargs):
        tools_list = kwargs.get("tools", self.tools)
        for struct_tool in tools_list:
            if tool.get('function', {}).get('name') == struct_tool.name:
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

                yield TextBlock("tool_resp_final", tool_resp)

    def handle_embedded_tool_call(self, tool_call, chat_memory, kwargs):
        if self.exec_tool:
            for block in self.execute_tool(tool_call, chat_memory, kwargs):
                if isinstance(block, TextBlock) and block.block_type == "tool_resp_final":
                    tool_resp = block.text
                    tool_resp_message = [
                        {
                            "role": "user",
                            "content": f'<tool_resp>{tool_resp}</tool_resp>'
                        }
                    ]
                    chat_memory.extend(tool_resp_message)
                    self.remember_response(tool_resp_message)
                yield block
