import json

from abc import abstractmethod
from typing import Union, List, Dict, Any

from ...utils import merge_blocks_by_index
from ...io import TextBlock, create_chk_block
from .base import Runnable

class ChatAgent(Runnable):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。
    """

    def __init__(self, threads_group: str=None, tools=None, toolkits=None, prompt:str=None, **kwargs):
        """
        对话智能体的几种基本行为：
        - 仅对话，不调用工具：不要提供 tools 参数
        - 推理出应当使用的工具，但不调用：仅提供 tools 参数，不提供 toolkits 参数
        - 推理出应当使用的工具，并调用：提供 tools 参数，同时提供 toolkits 参数
        """
        super().__init__(threads_group or "CHAT_AGENT", **kwargs)
        self.tools = tools or []
        self.toolkits = toolkits or []
        self.system_prompt = prompt

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        # 开始新对话
        new_chat = kwargs.pop("new_chat", False)
        locked_item = False

        _prompt = self._prepare_prompt(prompt)

        if isinstance(_prompt, List) and _prompt[0].get("role", "") == "system":
            new_chat = True
            locked_item = True

        # TODO: 应当在清空前做好历史管理
        if new_chat:
            self.memory.clear()

        toolkits = kwargs.get("toolkits", self.toolkits)
        resp = self.tools_calling(_prompt, *args, **kwargs) if toolkits else self.chat(_prompt, *args, **kwargs)

        for block in resp:
            yield block

        # 补充校验的尾缀
        if self.end_chk:
            yield create_chk_block(self.output)
        
        # 锁定记忆中的条数
        # 避免在提取短期记忆时被遗弃
        if locked_item:
            self.locked_items = len(self.memory)

    def _prepare_prompt(self, prompt: Union[str, List[dict]]) -> List[dict]:
        if isinstance(prompt, str) and self.system_prompt:
            return [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
        elif isinstance(prompt, List) and self.system_prompt:
            return [
                {"role": "system", "content": self.system_prompt},
                *prompt
            ]
        return prompt

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

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        pass