import json
import copy
import asyncio

from abc import abstractmethod
from typing import Union, List, Dict, Any, Set, Callable

from .....config import get_env
from .....utils import merge_tool_calls, extract_text, extract_final_answer, raise_invalid_params, filter_kwargs
from .....io import EventBlock, EndBlock, NewLineBlock
from ...base import Runnable
from ...message import Messages
from ..base import BaseAgent
from ..knowledge_manager import KnowledgeManager
from .tools_calling import BaseToolCalling, OpenAIToolsCalling
from .tools_manager import ToolsManager
from .memory_manager import MemoryManager
from .tfa_manager import TaskFinalAnswerManager

class ChatAgent(BaseAgent, KnowledgeManager, MemoryManager, ToolsManager, TaskFinalAnswerManager):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。

    ChatAgent 类包含一些核心属性，用于保存对话过程中的中间结果，例如：
    - task：用户发起的最初任务，这是 _task 的只读版本
    - final_answer：对话过程中输出的最终答案，这是 _final_answer 的只读版本
    - last_output：对话过程中上次调用输出的结果，这是 _last_output 的只读版本

    由于 final_answer 必须经过提示语引导，按照约定格式输出，因此可将 T/FA(task/final_answer) 用于自动化提取 Q/A 预料。
    而 T/FA 的提取结果可被保存在 __XP__ 等经验目录中，在其他对话时被当作检索资料调用。
    这就实现了基本的自我进化过程，而「自我进化」也是 illufly 设计的一个核心目标。
    """
    @classmethod
    def available_init_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "end_chk": "是否在最后输出一个 EndBlock",
            "start_marker": "开始标记，默认为 ```",
            "end_marker": "结束标记，默认为 ```",
            "final_answer_prompt": "最终答案提示词，可通过修改环境变量 ILLUFLY_FINAL_ANSWER_PROMPT 修改默认值",
            **BaseAgent.available_init_params(),
            **KnowledgeManager.available_init_params(),
            **ToolsManager.available_init_params(),
            **MemoryManager.available_init_params(),
        }

    def __init__(
        self,
        end_chk: bool = False,
        start_marker: str=None,
        end_marker: str=None,
        final_answer_prompt: str=None,
        **kwargs
    ):
        """
        对话智能体支持的核心能力包括：
        - tools：工具调用
        - memory：记忆管理
        - knowledge：知识管理
        """
        raise_invalid_params(kwargs, self.__class__.available_init_params())

        kwargs["tool_params"] = kwargs.get("tool_params", {"prompt": "详细描述用户问题"})
        BaseAgent.__init__(self, **filter_kwargs(kwargs, BaseAgent.available_init_params()))
        KnowledgeManager.__init__(self, **filter_kwargs(kwargs, KnowledgeManager.available_init_params()))
        ToolsManager.__init__(self, **filter_kwargs(kwargs, ToolsManager.available_init_params()))

        self.end_chk = end_chk

        self.start_marker = start_marker or "```"
        self.end_marker = end_marker or "```"

        self.final_answer_prompt = final_answer_prompt or get_env("ILLUFLY_FINAL_ANSWER_PROMPT")

        # 在子类中应当将模型参数保存到这个属性中，以便持久化管理
        self.model_args = {"base_url": None, "api_key": None}
        self.default_call_args = {"model": None}

        # 增加的可绑定变量
        self._task = ""
        self._final_answer = ""
        self._tools_to_exec = self.get_tools()
        self._resources = ""

        MemoryManager.__init__(self, **filter_kwargs(kwargs, MemoryManager.available_init_params()))

    def clear(self):
        self.memory.clear()
        self._task = ""
        self._final_answer = ""
        self._last_output = ""

    @property
    def task(self):
        return self._task

    @property
    def final_answer(self):
        return self._final_answer

    @property
    def runnable_info(self):
        info = super().runnable_info
        info.update({
            "model_name": self.default_call_args.get("model"),
            **self.model_args
        })
        return info

    @property
    def tools_calling_steps(self):
        """
        返回所有工具回调的计划和中间步骤
        """
        steps = []
        for h in self.tools_handlers:
            steps.extend(h.steps)
        return steps

    @property
    def provider_dict(self):
        local_dict = {
            "task": self.task,
            "final_answer": self.final_answer,
            "tools_calling_steps": self.tools_calling_steps,
            "tools_name": ",".join([a.name for a in self._tools_to_exec]),
            "tools_desc": "\n".join(json.dumps(t.tool_desc, ensure_ascii=False) for t in self._tools_to_exec),
            "knowledge": self.get_knowledge(self.task),
            "resources": self.get_resources(self.task),
        }
        return {
            **super().provider_dict,
            **{k:v for k,v in local_dict.items() if v is not None},
        }

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        raise NotImplementedError("ChatAgent 子类必须实现 generate 方法")
    
    async def async_generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        loop = asyncio.get_running_loop()
        for block in await self.run_in_executor(self.generate, prompt, *args, **kwargs):
            yield block

    def _fetch_final_output(self, output_text, chat_memory):
        final_output_text = extract_text(output_text, self.start_marker, self.end_marker)

        # 追加到短期记忆中
        chat_memory.append({
            "role": "assistant",
            "content": final_output_text
        })

        # 追加到长期记忆中
        self.remember_response(final_output_text)

        # 保存到最近输出
        self._last_output = final_output_text

        # 提取最终答案
        self._final_answer = extract_final_answer(final_output_text, self.final_answer_prompt)

        # 保存 T/FA 语料
        if self.thread_id and self.task and self.final_answer:
            self.save_tfa(self.thread_id, self.task, self.final_answer)

        return final_output_text

    def _handle_tool_calls(self, final_output_text, chat_memory, tools_behavior: str="none"):
        if "parse" in tools_behavior:
            for handler in self.tools_handlers:
                steps = handler.extract_tools_call(final_output_text)
                if steps and "execute" in tools_behavior:
                    for block in handler.handle(
                        steps,
                        short_term_memory=chat_memory,
                        long_term_memory=self.memory
                    ):
                        yield block

    def call(self, prompt: Any, *args, tools_behavior: str=None, **kwargs):
        """
        执行对话生成，并处理工具调用。

        illufly 的默认设计中有很多便利，比如自动执行工具回调。

        但这种默认设计有时也带来额外的困扰，例如，当你在工具回调之后想谈论刚刚的工具回调过程，而不是想调用它。
        此时，你可以使用 tools_behavior 参数临时修改对待工具回调的行为。
        """

        # 兼容 Runnable 类型，将其上一次的输出作为 prompt 输入
        if isinstance(prompt, Runnable):
            prompt = prompt.selected.last_output

        new_chat = kwargs.pop("new_chat", False)

        messages_std = Messages(prompt, style="text")
        self._task = messages_std[-1].content

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        # 重新绑定工具处理的 handlers
        for h in self.tools_handlers:
            h.reset(self._tools_to_exec)

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

            # 执行模型生成任务
            output_text, tools_call = "", []
            for block in self.generate(chat_memory, *args, **kwargs):
                yield block
                if block.block_type in ["chunk", "text"]:
                    output_text += block.text
                elif block.block_type == "final_text":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            openai_tools_calling_steps = merge_tool_calls(tools_call)
            if openai_tools_calling_steps:
                # 从返回参数中解析工具
                handler_openai = OpenAIToolsCalling(tools_to_exec=self._tools_to_exec)
                # 处理在返回结构中包含的 openai 风格的 tools-calling 工具调用，包括将结果追加到记忆中
                for block in handler_openai.handle(openai_tools_calling_steps, chat_memory, self.memory):
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        to_continue_call_llm = True
                    yield block
            else:
                final_output_text = self._fetch_final_output(output_text, chat_memory)
                yield EventBlock("final_text", final_output_text)

                _tools_behavior = tools_behavior or self.tools_behavior
                to_continue_call_llm = False
                for block in self._handle_tool_calls(final_output_text, chat_memory, _tools_behavior):
                    yield block
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        if "continue" in _tools_behavior:
                            to_continue_call_llm = True

        if self.end_chk:
            yield EndBlock(self.last_output)
        self.save_memory()

    async def async_call(self, prompt: Any, *args, tools_behavior: str=None, **kwargs):
        # 兼容 Runnable 类型，将其上一次的输出作为 prompt 输入
        if isinstance(prompt, Runnable):
            prompt = prompt.last_output

        new_chat = kwargs.pop("new_chat", False)

        messages_std = Messages(prompt, style="text")
        self._task = messages_std[-1].content

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)
        if "tools_desc" in self.get_bound_vars(Messages(prompt), new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        # 重新绑定工具处理的 handlers
        for h in self.tools_handlers:
            h.reset(self._tools_to_exec)

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
                if block.block_type in ["chunk", "text"]:
                    output_text += block.text
                elif block.block_type == "final_text":
                    output_text = block.text
                elif block.block_type == "tools_call_chunk":
                    tools_call.append(json.loads(block.text))

            final_tools_call = merge_tool_calls(tools_call)
            if final_tools_call:
                handler_openai = OpenAIToolsCalling(
                    short_term_memory=chat_memory,
                    long_term_memory=self.memory,
                    tools_to_exec=self._tools_to_exec
                )
                async for block in handler_openai.async_handle(final_tools_call):
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        to_continue_call_llm = True
                    yield block
            else:
                final_output_text = self._fetch_final_output(output_text, chat_memory)
                yield EventBlock("final_text", final_output_text)

                _tools_behavior = tools_behavior or self.tools_behavior
                to_continue_call_llm = False
                for block in self._handle_tool_calls(final_output_text, chat_memory, _tools_behavior):
                    yield block
                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        if "continue" in _tools_behavior:
                            to_continue_call_llm = True

        if self.end_chk:
            yield EndBlock(self.last_output)
        self.save_memory()
