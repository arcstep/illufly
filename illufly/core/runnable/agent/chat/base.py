import json
import copy
import asyncio

from abc import abstractmethod
from typing import Union, List, Dict, Any, Set, Callable

from .....utils import merge_tool_calls, extract_text
from .....io import EventBlock, EndBlock, NewLineBlock
from ...message import Messages
from ..base import BaseAgent
from ..knowledge_manager import KnowledgeManager
from .tools_manager import ToolsManager
from .memory_manager import MemoryManager
from .tools_calling import OpenAIToolsCalling, ToolCall

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
        self._resources = ""

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
    def last_output(self):
        return self.memory[-1]['content'] if self.memory else ""

    @property
    def provider_dict(self):
        local_dict = {
            "task": self._task,
            "tools_name": ",".join([a.name for a in self._tools_to_exec]),
            "tools_desc": "\n".join(json.dumps(t.tool_desc, ensure_ascii=False) for t in self._tools_to_exec),
            "knowledge": self.get_knowledge(self._task),
            "resources": self.get_resources(self._task),
        }
        return {
            **super().provider_dict,
            **{k:v for k,v in local_dict.items() if v is not None},
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

        messages_std = Messages(prompt, style="text")
        self._task = messages_std.messages[-1].content

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield EventBlock("info", f'记住 {remember_rounds} 轮对话')

        chat_memory = self.build_chat_memory(
            prompt=prompt, # 这里依然使用 prompt，而不是 messages_std，因为需要判断到底角色是 system 还是 user
            new_chat=new_chat,
            remember_rounds=remember_rounds
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
                handler_openai = OpenAIToolsCalling(
                    short_term_memory=chat_memory,
                    long_term_memory=self.memory,
                    tools_to_exec=self._tools_to_exec,
                    exec_tool=self.exec_tool
                )
                # 处理在返回结构中包含的 openai 风格的 tools-calling 工具调用，包括将结果追加到记忆中
                for block in handler_openai.handle_tools_call(final_tools_call, kwargs):
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
                handler_tool_call = ToolCall(
                    short_term_memory=chat_memory,
                    long_term_memory=self.memory,
                    tools_to_exec=self._tools_to_exec,
                    exec_tool=self.exec_tool
                )
                tool_calls = handler_tool_call.extract_tools_call(final_output_text)
                if tool_calls:
                    for index, tool_call in enumerate(tool_calls):
                        if index > 0:
                            new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                            chat_memory.append({
                                "role": "assistant",
                                "content": new_task
                            })
                            self.remember_response(new_task)
                        for block in handler_tool_call.handle_tools_call(tool_call, kwargs):
                            if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                                to_continue_call_llm = True
                            yield block

        if self.end_chk:
            yield EndBlock(self.last_output)

    async def async_call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        new_chat = kwargs.pop("new_chat", False)

        messages_std = Messages(prompt, style="text")
        self._task = messages_std.messages[-1].content
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield EventBlock("info", f'记住 {remember_rounds} 轮对话')

        chat_memory = self.build_chat_memory(
            prompt=prompt,
            new_chat=new_chat,
            remember_rounds=remember_rounds
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
                handler_openai = OpenAIToolsCalling(
                    short_term_memory=chat_memory,
                    long_term_memory=self.memory,
                    tools_to_exec=self._tools_to_exec,
                    exec_tool=self.exec_tool
                )
                async for block in handler_openai.async_handle_tools_call(final_tools_call, kwargs):
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

                handler_tool_call = ToolCall(
                    short_term_memory=chat_memory,
                    long_term_memory=self.memory,
                    tools_to_exec=self._tools_to_exec,
                    exec_tool=self.exec_tool
                )
                tool_calls = handler_tool_call.extract_tools_call(final_output_text)
                if tool_calls:
                    for index, tool_call in enumerate(tool_calls):
                        if index > 0:
                            new_task = f'请继续: {json.dumps(tool_call, ensure_ascii=False)}'
                            chat_memory.append({
                                "role": "assistant",
                                "content": new_task
                            })
                            self.remember_response(new_task)
                        async for block in handler_tool_call.async_handle_tools_call(tool_call, kwargs):
                            if isinstance(block, EventBlock) and block.block_type == "tool_resp_final":
                                to_continue_call_llm = True
                            yield block

        if self.end_chk:
            yield EndBlock(self.last_output)
