import json
import copy
import asyncio
import uuid

from abc import abstractmethod
from typing import Union, List, Tuple, Set, Any

from .....config import get_env
from .....utils import merge_tool_calls, extract_text, raise_invalid_params, filter_kwargs
from .....io import EventBlock, EndBlock, NewLineBlock
from ....document import Document
from ...base import Runnable
from ...message import Messages
from ...prompt_template import PromptTemplate
from ...vectordb import VectorDB
from ..retriever import Retriever
from ..base import BaseAgent
from ..knowledge_manager import KnowledgeManager
from .tools_calling import BaseToolCalling, OpenAIToolsCalling
from .tools_manager import ToolsManager
from .memory_manager import MemoryManager

class ChatAgent(BaseAgent, KnowledgeManager, MemoryManager, ToolsManager):
    """
    对话智能体是基于大模型实现的智能体，可以用于对话生成、对话理解等场景。
    """

    @classmethod
    def help(cls):
        """
        返回当前可用的参数列表。
        """
        return f'{cls.__doc__ or ChatAgent.__doc__}\n\n{cls.__name__} 参数列表：\n' + "\n".join([f"- {k}: {v}" for k, v in cls.allowed_params().items()])

    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "end_chk": "是否在最后输出一个 EndBlock",
            "fetching_context": "上下文提取标记，可通过修改环境变量 ILLUFLY_CONTEXT_START 和 ILLUFLY_CONTEXT_END 修改默认值",
            "fetching_final_answer": "最终答案提取标记，可通过修改环境变量 ILLUFLY_FINAL_ANSWER_START 和 ILLUFLY_FINAL_ANSWER_END 修改默认值",
            "fetching_output": "输出内容提取标记",
            "chat_learn_folder": "知识库目录，可通过修改环境变量 ILLUFLY_CHAT_LEARN 修改默认值",
            "default_docs": "默认文档目录，可通过修改环境变量 ILLUFLY_DOCS 修改默认值",
            **BaseAgent.allowed_params(),
            **KnowledgeManager.allowed_params(),
            **ToolsManager.allowed_params(),
            **MemoryManager.allowed_params(),
        }

    def __init__(
        self,
        end_chk: bool = False,
        fetching_context: Tuple[str, str]=None,
        fetching_final_answer: Tuple[str, str]=None,
        fetching_output: Tuple[str, str]=None,
        chat_learn_folder: str=None,
        default_docs: Set[str]=None,
        **kwargs
    ):
        """
        对话智能体支持的核心能力包括：
        - tools：工具调用
        - memory：记忆管理
        - knowledge：知识管理
        """
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        kwargs["tool_params"] = kwargs.get("tool_params", {"prompt": "详细描述用户问题"})
        BaseAgent.__init__(self, **filter_kwargs(kwargs, BaseAgent.allowed_params()))
        KnowledgeManager.__init__(self, **filter_kwargs(kwargs, KnowledgeManager.allowed_params()))
        ToolsManager.__init__(self, **filter_kwargs(kwargs, ToolsManager.allowed_params()))

        self.end_chk = end_chk

        self.fetching_context = fetching_context or (get_env("ILLUFLY_CONTEXT_START"), get_env("ILLUFLY_CONTEXT_END"))
        self.fetching_final_answer = fetching_final_answer or (get_env("ILLUFLY_FINAL_ANSWER_START"), get_env("ILLUFLY_FINAL_ANSWER_END"))
        self.fetching_output = fetching_output or (get_env("ILLUFLY_OUTPUT_START"), get_env("ILLUFLY_OUTPUT_END"))

        # 在子类中应当将模型参数保存到这个属性中，以便持久化管理
        self.model_args = {"base_url": None, "api_key": None}
        self.default_call_args = {"model": None}

        # 增加的可绑定变量
        self._task = ""
        self._final_answer = ""
        self._tools_to_exec = self.get_tools()
        self._resources = ""

        MemoryManager.__init__(self, **filter_kwargs(kwargs, MemoryManager.allowed_params()))

        self.chat_learn_folder = chat_learn_folder or get_env("ILLUFLY_CHAT_LEARN")
        self.default_docs = default_docs or set({get_env("ILLUFLY_DOCS"), self.chat_learn_folder})
        self.load_default_knowledge()

    def clear(self):
        self.memory.clear()
        self._task = ""
        self._final_answer = ""
        self._last_output = ""

    def load_default_knowledge(self):
        """
        加载默认知识库。
        """
        for item in self.knowledge:
            if not isinstance(item, (str, Document, VectorDB, Retriever)):
                raise ValueError("Knowledge list items MUST be str, Document or VectorDB")

            if isinstance(item, VectorDB):
                if not self.default_vdb:
                    self.default_vdb = item
                if item in item.sources:
                    # 如果已经在向量库中指定了文档目录，则不再从默认文档目录中加载
                    self.default_docs.remove(item)

        if self.default_vdb:
            for doc_folder in self.default_docs:
                self.default_vdb.load(dir=doc_folder)

    def clone_chat_learn(self, dest: str, src: str=None):
        """
        克隆 illufly 自身的聊天问答经验。
        """
        if not os.path.exists(dest):
            os.makedirs(dest)

        files_count = 0
        src = self.chat_learn_folder
        for item in os.listdir(src):
            if item.startswith('.'):
                continue
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dest, item)
            if os.path.isdir(src_path):
                # 如果是目录，递归拷贝
                self.clone_chat_learn(dst_path, src_path)
            else:
                # 如果是文件，直接拷贝
                shutil.copy2(src_path, dst_path)
                files_count += 1
        return f"从 {src} 拷贝到 {dest} 完成，共克隆了 {files_count} 个文件。"

    def clear_chat_learn(self):
        """
        清空聊天问答经验。
        """
        src = self.chat_learn_folder
        if os.path.exists(src):
            shutil.rmtree(src)

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
            "thread_id": self.thread_id,
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
            "recalled_knowledge": self.recalled_knowledge,
            "chat_memory": self.chat_memory
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
        # 提取最终答案
        self._final_answer = extract_text(output_text, self.fetching_final_answer, strict=True)

        # 提取上下文
        context = extract_text(output_text, self.fetching_context, strict=True)

        # 提取输出内容
        final_output_text = extract_text(output_text, self.fetching_output, strict=False)

        # 保存到最近输出
        self._last_output = final_output_text

        messages = Messages([("ai", final_output_text)], style=self.style).to_list()
        # 追加到短期记忆中
        chat_memory.extend(messages)
        # 追加到长期记忆中
        self.remember_response(messages)

        return {
            "final_output_text": final_output_text,
            "context": context
        }

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

    def _patch_knowledge(self, messages: Messages):
        """
        根据当前的记忆和知识，对提示语进行补充。

        补充内容包括：
        - 默认保存在 __DOCS__ 目录中的已有知识
        - 默认保存在临时目录中的经验信息
        - 已经添加的资源信息
        """
        kg = ""
        existing_text = "\n".join([m['content'] for m in Messages(messages).to_list(style="text")])
        if self.knowledge:
            for item in self.get_knowledge(self.task):
                if item not in existing_text:
                    kg += item
        patch_info = ""
        if kg:
            patch_info += f"回答时请参考已有知识：\n@knowledge\n{kg}\n"
        if patch_info:
            add_messages = Messages([
                ("user", patch_info),
                ("assistant", "ok")
            ], style=self.style).to_list()

            self.memory.insert(-1, add_messages[0])
            self.memory.insert(-1, add_messages[1])

            messages.insert(-1, add_messages[0])
            messages.insert(-1, add_messages[1])

        return messages

    def call(self, prompt: Any, tools_behavior: str=None, **kwargs):
        """
        执行对话生成，并处理工具调用。

        illufly 的默认设计中有很多便利，比如自动执行工具回调。

        但这种默认设计有时也带来额外的困扰，例如，当你在工具回调之后想谈论刚刚的工具回调过程，而不是想调用它。
        此时，你可以使用 tools_behavior 参数临时修改对待工具回调的行为。
        """

        # 兼容 Runnable 类型，将其上一次的输出作为 prompt 输入
        if not isinstance(prompt, PromptTemplate) and isinstance(prompt, Runnable):
            prompt = prompt.selected.last_output

        new_chat = kwargs.pop("new_chat", False)

        messages_std = Messages(prompt, style="text")
        self._task = messages_std.to_list()[-1]['content']
        yield self.create_event_block("user", self._task)
        yield self.create_event_block("agent", self.name)

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)
        if "tools_desc" in self.get_bound_vars(messages_std, new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", [])) or None

        # 重新绑定工具处理的 handlers
        for h in self.tools_handlers:
            h.reset(self._tools_to_exec)

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield self.create_event_block("info", f'记住 {remember_rounds} 轮对话')

        chat_memory = self.build_chat_memory(
            prompt=prompt, # 这里依然使用 prompt
            new_chat=new_chat,
            remember_rounds=remember_rounds
        )
        chat_memory = self._patch_knowledge(chat_memory)
        if self.recalled_knowledge:
            kg_source = {}
            for item in self.recalled_knowledge:
                if isinstance(item, Document):
                    src = item.meta.get("source", "无来源文档")
                else:
                    src = "直接资料"
                if src not in kg_source:
                    kg_source[src] = []
                kg_source[src].append(item)
            for k, v in kg_source.items():
                yield self.create_event_block("RAG", f"{k}：发现 {len(v)} 条资料")

        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False

            # 执行模型生成任务
            output_text, tools_call = "", []
            content_id = str(uuid.uuid1().hex)

            for block in self.generate(chat_memory, **kwargs):
                block.content_id = content_id
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
                    block.content_id = content_id
                    yield block

                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        to_continue_call_llm = True
            else:
                final_output_text = self._fetch_final_output(output_text, chat_memory)
                yield self.create_event_block("final_text", final_output_text["final_output_text"], content_id=content_id)
                if final_output_text["context"]:
                    yield self.create_event_block("context", final_output_text["context"], content_id=content_id)

                _tools_behavior = tools_behavior or self.tools_behavior
                to_continue_call_llm = False
                for block in self._handle_tool_calls(final_output_text["final_output_text"], chat_memory, _tools_behavior):
                    block.content_id = content_id
                    yield block

                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        if "continue" in _tools_behavior:
                            to_continue_call_llm = True

        if self.end_chk:
            yield EndBlock(self.last_output)
        self.save_memory()

    async def async_call(self, prompt: Any, tools_behavior: str=None, **kwargs):
        # 兼容 Runnable 类型，将其上一次的输出作为 prompt 输入
        if not isinstance(prompt, PromptTemplate) and isinstance(prompt, Runnable):
            prompt = prompt.selected.last_output

        new_chat = kwargs.pop("new_chat", False)

        messages_std = Messages(prompt, style="text")
        self._task = messages_std.to_list()[-1]['content']
        yield self.create_event_block("user", self._task)
        yield self.create_event_block("agent", self.name)

        # 根据模板中是否直接使用 tools_desc 来替换 tools 参数
        self._tools_to_exec = self.get_tools(kwargs.get("tools", []))
        for tool in self._tools_to_exec:
            self.bind_consumer(tool, dynamic=True)
        if "tools_desc" in self.get_bound_vars(messages_std, new_chat=new_chat):
            kwargs["tools"] = None
        else:
            kwargs["tools"] = self.get_tools_desc(kwargs.get("tools", []))

        # 重新绑定工具处理的 handlers
        for h in self.tools_handlers:
            h.reset(self._tools_to_exec)

        remember_rounds = kwargs.pop("remember_rounds", self.remember_rounds)
        yield self.create_event_block("info", f'记住 {remember_rounds} 轮对话')

        chat_memory = self.build_chat_memory(
            prompt=prompt,
            new_chat=new_chat,
            remember_rounds=remember_rounds
        )
        chat_memory = self._patch_knowledge(chat_memory)

        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False

            output_text, tools_call = "", []
            content_id = str(uuid.uuid1().hex)

            async for block in self.async_generate(chat_memory, **kwargs):
                block.content_id = content_id
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
                async for block in handler_openai.async_handle(openai_tools_calling_steps, chat_memory, self.memory):
                    block.content_id = content_id
                    if block.block_type == "chunk":
                        block.block_type = "tool_resp_chunk"
                    elif block.block_type == "text":
                        block.block_type = "tool_resp_text"
                    yield block

                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        to_continue_call_llm = True

            else:
                final_output_text = self._fetch_final_output(output_text, chat_memory)
                yield self.create_event_block("final_text", final_output_text["final_output_text"], content_id=content_id)
                if final_output_text["context"]:
                    yield self.create_event_block("context", final_output_text["context"], content_id=content_id)

                _tools_behavior = tools_behavior or self.tools_behavior
                to_continue_call_llm = False
                for block in self._handle_tool_calls(final_output_text["final_output_text"], chat_memory, _tools_behavior):
                    block.content_id = content_id
                    if block.block_type == "chunk":
                        block.block_type = "tool_resp_chunk"
                    elif block.block_type == "text":
                        block.block_type = "tool_resp_text"
                    yield block

                    if isinstance(block, EventBlock) and block.block_type == "final_tool_resp":
                        if "continue" in _tools_behavior:
                            to_continue_call_llm = True

        if self.end_chk:
            yield EndBlock(self.last_output)
        self.save_memory()
