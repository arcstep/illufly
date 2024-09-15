import json
import copy

from abc import abstractmethod
from typing import Union, List, Dict, Any

from ..utils import merge_blocks_by_index, extract_text
from ..io import TextBlock, create_chk_block
from ..tools import PythonCodeTool

from .base import Runnable

class ChatAgent(Runnable):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。
    """

    def __init__(self, threads_group: str=None, start_marker: str=None, end_marker: str=None, **kwargs):
        """
        对话智能体的几种基本行为：
        - 仅对话，不调用工具：不要提供 tools 参数
        - 推理出应当使用的工具，但不调用：仅提供 tools 参数，不提供 toolkits 参数
        - 推理出应当使用的工具，并调用：提供 tools 参数，同时提供 toolkits 参数
        """
        super().__init__(threads_group or "CHAT_AGENT", **kwargs)

        self.update_python_code_tool()

        self.start_marker = start_marker or "```"
        self.end_marker = end_marker or "```"

        # 在子类中应当将模型参数保存到这个属性中，以便持久化管理
        self.model_args = {}
        self.default_call_args = {}
    
    def update_python_code_tool(self):
        if self.data:
            agent = self.clone(memory=[Template(template_id or "GEN_CODE_PANDAS"), "请开始生成代码"])
            self.prepared_tools = [PythonCodeTool(self.data, agent)]

    def add_dataset(self, *args, **kwargs):
        super().add_dataset(*args, **kwargs)
        self.update_python_code_tool()

    def clone(self):
        new_obj = super().clone()
        new_obj.model_args = copy.deepcopy(self.model_args)
        new_obj.default_call_args = copy.deepcopy(self.default_call_args)
        new_obj._tools = copy.deepcopy(self._tools)
        return new_obj

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        if not isinstance(prompt, str) and not isinstance(prompt, list):
            raise ValueError("prompt 必须是字符串或消息列表")

        # 开始新对话
        new_chat = kwargs.pop("new_chat", False)
        locked_item = False
        new_task_flag = False

        # 此处设置工作台变量：task
        self.set_task(prompt if isinstance(prompt, str) else prompt[-1].get("content"))

        if isinstance(prompt, List) and prompt[0].get("role", "") == "system":
            new_chat = True
            locked_item = True

        # TODO: 应当在清空前做好历史管理
        if new_chat:
            self.memory.clear()
            new_task_flag = True
        
        if not self.memory:
            new_task_flag = True

        # 根据实例初始化时的 memory 考虑是否补充记忆
        self.confirm_memory_init()

        # 如果在提示语模板中已经被使用，就不再追加到记忆中
        if new_task_flag and "task" in self.init_memory.input_vars:
            _prompt = []
        else:
            _prompt = prompt

        toolkits = kwargs.get("toolkits", self.toolkits)
        if self.exec_tool and not kwargs.get("tools", None):
            resp = self.chat_with_tools_calling(_prompt, *args, **kwargs)
        else:
            resp = self.only_chat(_prompt, *args, **kwargs)

        for block in resp:
            yield block

        # 补充校验的尾缀
        if self.end_chk:
            yield create_chk_block(self.output)
        
        # 锁定记忆中的条数
        # 避免在提取短期记忆时被遗弃
        if locked_item:
            self.locked_items = len(self.memory)

    def only_chat(self, prompt: Union[str, List[dict]], *args, **kwargs):
        messages = self.get_chat_memory(knowledge=self.get_knowledge())
        messages.extend(self.create_new_memory(prompt))

        output_text = ""
        tools_call = []
        # 调用大模型
        for block in self.generate(messages, *args, **kwargs):
            yield block
            if block.block_type == "chunk":
                output_text += block.content
            elif block.block_type == "tools_call_chunk":
                tools_call.append(json.loads(block.text))
            elif block.block_type == "text_final":
                output_text = block.text

        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            content = json.dumps(final_tools_call, ensure_ascii=False)
            self.remember_response(content)
            yield TextBlock("tools_call_final", content)
        else:
            if output_text:
                final_output_text = extract_text(output_text, self.start_marker, self.end_marker)
                self.remember_response(final_output_text)
                yield TextBlock("text_final", final_output_text)

    def chat_with_tools_calling(self, prompt: Union[str, List[dict]], *args, **kwargs):
        toolkits = kwargs.pop("toolkits", self.toolkits)

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

            # 合并工具回调
            final_tools_call = merge_blocks_by_index(tools_call)            
            if final_tools_call:
                # 记录工具回调提示
                final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
                yield TextBlock("tools_call_final", final_tools_call_text)
                tools_call_message = [
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": final_tools_call_text
                    }
                ]
                messages.extend(tools_call_message)
                self.remember_response(tools_call_message)
                # 执行工具回调
                # 如果大模型的结果返回多个工具回调，则要逐个调用完成才能继续下一轮大模型的问调用。
                for index, tool in final_tools_call.items():
                    for struct_tool in toolkits:
                        if tool['function']['name'] == struct_tool.tool['function']['name']:
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
                self.remember_response(output_text)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        raise NotImplementedError("子类必须实现 generate 方法")
