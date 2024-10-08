import json
import copy
import asyncio

from abc import abstractmethod
from typing import Union, List, Dict, Any, Set, Callable

from .....utils import merge_tool_calls, extract_text
from .....io import EventBlock, EndBlock, NewLineBlock

from ..base import BaseAgent
from ..memory_manager import MemoryManager
from ..message import Messages
from ..knowledge_manager import KnowledgeManager
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
        kwargs["tool_params"] = kwargs.get("tool_params", {"prompt": "详细描述用户问题"})
        BaseAgent.__init__(self, **kwargs)
        KnowledgeManager.__init__(self, **kwargs)
        ToolsManager.__init__(self, **kwargs)

        self.end_chk = end_chk

        self.start_marker = start_marker or "```"
        self.end_marker = end_marker or "```"

        # 在子类中应当将模型参数保存到这个属性中，以便持久化管理
        self.model_args = {"base_url": None, "api_key": None}
        self.default_call_args = {"model": None}

        # 增加的可绑定变量
        self._task = ""
        self._tools_to_exec = self.get_tools()
        MemoryManager.__init__(self, **kwargs)
    
    @property
    def runnable_info(self):
        info = super().runnable_info
        info.update({
            "model_name": self.default_call_args.get("model"),
            **self.model_args
        })
        return info

    @property
    def last_input(self):
        return self._last_input.last_content if self._last_input else None

    @property
    def last_output(self):
        return self.memory[-1]['content'] if self.memory else ""

    @property
    def task(self):
        return self._task

    @property
    def provider_dict(self):
        return {
            **super().provider_dict,
            "task": self.task,
            "tools_name": self.get_tools_name(),
            "tools_desc": "\n".join(json.dumps(t.tool_desc, ensure_ascii=False) for t in self._tools_to_exec),
        }

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        raise NotImplementedError("子类必须实现 generate 方法")
    
    async def async_generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        loop = asyncio.get_running_loop()
        for block in await self.run_in_executor(self.generate, prompt, *args, **kwargs):
            yield block

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        new_chat = kwargs.pop("new_chat", False)
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield EventBlock("info", f'记住 {remember_rounds} 轮对话')

        messages_std = Messages(prompt, style="text")
        knowledge = kwargs.pop("knowledge", self.get_knowledge(messages_std.messages[-1].content))
        knowledge += self.get_resources()

        chat_memory = self.get_chat_memory(
            prompt=prompt,
            new_chat=new_chat,
            remember_rounds=remember_rounds,
            knowledge=knowledge
        )

        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False
            output_text, tools_call = "", []

            # 执行模型生成任务
            for block in self.generate(chat_memory, *args, **kwargs):
                yield block
                if block.block_type == "chunk":
                    output_text += block.text
                elif block.block_type == "text_final":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            final_tools_call = merge_tool_calls(tools_call)
            if final_tools_call:
                # 处理在返回结构中包含的 openai 风格的 tools-calling 工具调用，包括将结果追加到记忆中
                for block in self._handle_openai_style_tools_call(final_tools_call, chat_memory, kwargs):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        to_continue_call_llm = True
                    yield block
            else:
                final_output_text = extract_text(output_text, self.start_marker, self.end_marker)
                chat_memory.append({
                    "role": "assistant",
                    "content": final_output_text
                })
                self.remember_response(final_output_text)
                yield EventBlock("text_final", final_output_text)

                # 处理直接在文本中包含的 <tool_call> 风格的工具调用，包括将结果追加到记忆中
                tool_calls = self.extract_in_text_tool_calls(final_output_text)
                if tool_calls:
                    for index, tool_call in enumerate(tool_calls):
                        if index > 0:
                            new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                            chat_memory.append({
                                "role": "assistant",
                                "content": new_task
                            })
                            self.remember_response(new_task)
                        for block in self._handle_in_text_tool_call(tool_call, chat_memory, kwargs):
                            if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                                to_continue_call_llm = True
                            yield block

        if self.end_chk:
            yield EndBlock(self.last_output)

    async def async_call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        new_chat = kwargs.pop("new_chat", False)
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield EventBlock("info", f'记住 {remember_rounds} 轮对话')

        messages_std = Messages(prompt, style="text")
        knowledge = kwargs.pop("knowledge", self.get_knowledge(messages_std[-1].content))
        knowledge += self.get_resources()

        chat_memory = self.get_chat_memory(
            prompt=prompt,
            new_chat=new_chat,
            remember_rounds=remember_rounds,
            knowledge=knowledge
        )

        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False
            output_text, tools_call = "", []

            async for block in self.async_generate(chat_memory, *args, **kwargs):
                yield block
                if block.block_type == "chunk":
                    output_text += block.text
                elif block.block_type == "text_final":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            final_tools_call = merge_tool_calls(tools_call)
            if final_tools_call:
                async for block in self._async_handle_openai_style_tools_call(final_tools_call, chat_memory, kwargs):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        to_continue_call_llm = True
                    yield block
            else:
                final_output_text = extract_text(output_text, self.start_marker, self.end_marker)
                chat_memory.append({
                    "role": "assistant",
                    "content": final_output_text
                })
                self.remember_response(final_output_text)
                yield EventBlock("text_final", final_output_text)

                tool_calls = self.extract_in_text_tool_calls(final_output_text)
                if tool_calls:
                    for index, tool_call in enumerate(tool_calls):
                        if index > 0:
                            new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                            chat_memory.append({
                                "role": "assistant",
                                "content": new_task
                            })
                            self.remember_response(new_task)
                        async for block in self._async_handle_in_text_tool_call(tool_call, chat_memory, kwargs):
                            if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                                to_continue_call_llm = True
                            yield block

        if self.end_chk:
            yield EndBlock(self.last_output)

    def _handle_openai_style_tools_call(self, final_tools_call, chat_memory, kwargs):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield NewLineBlock()
        yield EventBlock("tools_call_final", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]

            if self.exec_tool:
                # 记忆追加
                chat_memory.extend(tools_call_message)
                self.remember_response(tools_call_message)

                for block in self._execute_tool(tool, kwargs):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        chat_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        self.remember_response(tool_resp_message)
                    yield block

    async def _async_handle_openai_style_tools_call(self, final_tools_call, chat_memory, kwargs):
        final_tools_call_text = json.dumps(final_tools_call, ensure_ascii=False)
        yield EventBlock("tools_call_final", final_tools_call_text)

        for index, tool in enumerate(final_tools_call):
            tools_call_message = [{
                "role": "assistant",
                "content": "",
                "tool_calls": [tool]
            }]
            if self.exec_tool:
                # 记忆追加
                chat_memory.extend(tools_call_message)
                self.remember_response(tools_call_message)

                async for block in self._async_execute_tool(tool, kwargs):
                    if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                        tool_resp = block.text
                        tool_resp_message = [{
                            "tool_call_id": tool['id'],
                            "role": "tool",
                            "name": tool['function']['name'],
                            "content": tool_resp
                        }]
                        # 短期记忆追加
                        chat_memory.extend(tool_resp_message)
                        # 长期记忆追加
                        self.remember_response(tool_resp_message)
                    yield block

    def _execute_tool(self, tool, kwargs):
        for struct_tool in self._tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""
                print("tool_args", tool_args)

                self.bind_consumers(struct_tool)
                tool_func_result = struct_tool.call(**tool_args)
                for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "tool_resp_final":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield EventBlock("tool_resp_chunk", x)
                yield NewLineBlock()
                yield EventBlock("tool_resp_final", tool_resp)

    async def _async_execute_tool(self, tool, kwargs):
        for struct_tool in self._tools_to_exec:
            if tool.get('function', {}).get('name') == struct_tool.name:
                tool_args = struct_tool.parse_arguments(tool['function']['arguments'])
                tool_resp = ""

                tool_func_result = struct_tool.async_call(**tool_args)
                async for x in tool_func_result:
                    if isinstance(x, EventBlock):
                        if x.block_type == "tool_resp_final":
                            tool_resp = x.text
                        elif x.block_type == "chunk":
                            tool_resp += x.text
                        yield x
                    else:
                        tool_resp += x
                        yield EventBlock("tool_resp_chunk", x)

                yield NewLineBlock()
                yield EventBlock("tool_resp_final", tool_resp)

    def _handle_in_text_tool_call(self, tool_call, chat_memory, kwargs):
        if self.exec_tool:
            for block in self._execute_tool(tool_call, kwargs):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
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

    async def _async_handle_in_text_tool_call(self, tool_call, chat_memory, kwargs):
        if self.exec_tool:
            async for block in self._async_execute_tool(tool_call, kwargs):
                if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
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

    def extract_in_text_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        start_marker = "<tool_call>"
        end_marker = "</tool_call>"
        start = text.find(start_marker)
        while start != -1:
            end = text.find(end_marker, start)
            if end != -1:
                tool_call_json = text[start + len(start_marker):end]
                try:
                    tool_call = json.loads(tool_call_json)
                    tool_calls.append({
                        "function": {
                            "name": tool_call.get("name"),
                            "arguments": json.dumps(tool_call.get("arguments", "[]"), ensure_ascii=False)
                        }
                    })
                except json.JSONDecodeError:
                    pass
                start = text.find(start_marker, end)
            else:
                break
        return tool_calls