import asyncio
import re
import os
import json
import hashlib
from threading import Thread

from typing import List, Dict, Any
from langchain_core.utils.function_calling import convert_to_openai_tool

from ..config import get_env
from ..io import create_chk_block, merge_blocks_by_index, TextBlock
from ..hub import load_chat_template
from ..tools import create_python_code_tool
from ..utils import compress_text

from .markdown import Markdown, parse_markdown
from .history import History
from .state import State

import pandas as pd

class Agent:
    def __init__(self, llm, toolkits: list=[], tools: list=[], k: int=10, history: History=None, **model_kwargs):
        """
        Args:
        - llm: 调用模型的函数
        - toolkits: 智能体回调工具包
        - k: 保留的历史消息轮数，每轮包括问和答共2条消息
        - history: 对话涉及的大模型调用历史记录
        """

        self.llm = llm
        self.history = history
        self.k = k
        self.model_kwargs = model_kwargs

        self._toolkits = toolkits or []
        self._tools = tools or []

        # 状态数据
        self.state = State()

    def __str__(self):
        return f"Desk(state={self.state.__repr__()})"
    
    def __repr__(self):
        return f"Desk(state={self.state.__repr__()})"
    
    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.state.add_dataset(name, df, desc)
    
    def add_knowledge(self, knowledge: str):
        self.state.add_knowledge(knowledge)
    
    @property
    def tools(self):
        python_code_tool = create_python_code_tool(self.state.data, self.llm, **self.model_kwargs)
        return self._tools + [convert_to_openai_tool(python_code_tool)]
    
    @property
    def toolkits(self):
        python_code_tool = create_python_code_tool(self.state.data, self.llm, **self.model_kwargs)
        return self._toolkits + [python_code_tool]

    @property
    def output(self):
        return self.state.output

    @property
    def messages(self):
        return self.state.messages

    @property
    def last(self):
        return self.state.messages[-1]['content']
    
    @property
    def from_outline(self):
        return self.state.from_outline

    def append_knowledge_to_messages(self, messages: List[Any]):
        """
        将知识库中的知识追加到消息列表中。
        """
        existing_contents = {msg['content'] for msg in messages if msg['role'] == 'user'}
        
        for kg in self.state.get_knowledge():
            content = f'已知：{kg}'
            if content not in existing_contents:
                messages.extend([{
                    'role': 'user',
                    'content': content
                },
                {
                    'role': 'assistant',
                    'content': 'OK, 我将利用这个知识回答后面问题。'
                }])
        return messages
    
    async def achat(self, question:str, toolkits=[], tools=[], llm=None, new_chat:bool=False, k:int=None, **model_kwargs):
        """
        异步版本的 chat 方法。
        """
        new_messages = [{
            'role': 'user',
            'content': question
        }]

        long_term_memory = self.state.messages
        if new_chat:
            long_term_memory.clear()

        short_term_memory = self.get_chat_memory(k)
        short_term_memory.extend(new_messages)

        self.append_knowledge_to_messages(long_term_memory)
        long_term_memory.extend(new_messages)

        self.model_kwargs.update(model_kwargs)
        async for block in self._acall(
            llm=llm or self.llm,
            long_term_memory=long_term_memory,
            short_term_memory=short_term_memory,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            **model_kwargs
        ):
            yield block

    def get_chat_memory(self, k:int=None):
        _k = self.k if k is None else k
        long_term_memory = self.state.messages

        final_k = 2 * _k if _k >= 1 else 1
        if len(long_term_memory) > 0 and long_term_memory[0]['role'] == 'system':
            new_memory = long_term_memory[:self.state.reserved_k]
            new_memory += long_term_memory[self.state.reserved_k:][-final_k:]
        else:
            new_memory = long_term_memory[-final_k:]

        self.append_knowledge_to_messages(new_memory)

        return new_memory

    def chat(self, question:str, toolkits=[], tools=[], llm=None, new_chat:bool=False, k:int=None, **model_kwargs):
        """
        多轮对话时，将对话记录追加到状态数据中的消息列表。
        但如果指定新对话，则首先清空消息列表。

        请注意，执行`chat`指令时，输出不会影响到 output 属性。
        """
        new_messages = [{
            'role': 'user',
            'content': question
        }]

        long_term_memory = self.state.messages
        if new_chat:
            long_term_memory.clear()

        short_term_memory = self.get_chat_memory(k)
        short_term_memory.extend(new_messages)

        self.append_knowledge_to_messages(long_term_memory)
        long_term_memory.extend(new_messages)

        self.model_kwargs.update(model_kwargs)
        resp = self._call(
            llm=llm or self.llm,
            long_term_memory=long_term_memory,
            short_term_memory=short_term_memory,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            **model_kwargs
        )
        for block in resp:
            yield block

    def write(self, input:Dict[str, Any], template: str=None, toolkits=[], tools=[], question:str=None, llm=None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。

        每次执行`write`指令时，输出的内容将保存到 state 中的 markdown 属性。
        """
        
        _input = {"task": input} if isinstance(input, str) else input
        _question = question
        if self.state.data:
            _question = "请根据需要调用工具查询真实数据。"

        # 重置消息列表
        long_term_memory = self.state.messages

        self.model_kwargs.update(model_kwargs)
        resp = self._write(
            _input,
            template=template,
            long_term_memory=long_term_memory,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            question=_question,
            llm=llm or self.llm,
            **self.model_kwargs
        )

        for block in resp:
            yield block

        # 针对 write 指令结果对话时，将当前消息列表的长度作为 reserved_k
        self.state.reserved_k = len(long_term_memory)
        # 将最终生成结果保存到 markdown 中
        self.state.markdown = Markdown(long_term_memory[-1]['content'])

    async def awrite(self, input:Dict[str, Any], template: str=None, toolkits=[], tools=[], question:str=None, llm=None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。

        每次执行`write`指令时，输出的内容将保存到 state 中的 markdown 属性。
        """
        
        _input = {"task": input} if isinstance(input, str) else input
        _question = question
        if self.state.data:
            _question = "请根据需要调用工具查询真实数据。"

        # 重置消息列表
        long_term_memory = self.state.messages

        self.model_kwargs.update(model_kwargs)
        async for block in self._awrite(
            _input,
            template=template,
            long_term_memory=long_term_memory,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            question=_question,
            llm=llm or self.llm,
            **self.model_kwargs
        ):
            yield block

        # 针对 write 指令结果对话时，将当前消息列表的长度作为 reserved_k
        self.state.reserved_k = len(long_term_memory)
        # 将最终生成结果保存到 markdown 中
        self.state.markdown = Markdown(long_term_memory[-1]['content'])

    def from_outline(self, toolkits=[], tools=[], question:str=None, llm=None, prev_k:int=1000, next_k:int=500, **model_kwargs):
        """
        从工作台中指定的提纲执行扩写任务。

        每次执行`from_outline`指令时，输出的内容将保存到 state 中的 from_outline 属性。
        """
        outline = self.state.outline
        md = self.state.markdown
        _question = question
        if self.state.data:
            _question = "请根据需要调用工具查询真实数据。"

        if outline:
            for doc in outline:
                # 初始化为空的消息列表
                outline_id = doc.metadata['id']
                self.state.from_outline[outline_id] = []

                long_term_memory = self.state.from_outline[outline_id]

                (draft, task) = md.fetch_outline_task(doc, prev_k=prev_k, next_k=next_k)
                yield TextBlock("info", f"执行扩写任务 <{outline_id}>：\n{task}")
                draft_md = f'```markdown\n{draft}\n```'
                task_md = f'```markdown\n{task}\n```'
                resp = self._write(
                    input={"draft": draft_md, "task": task_md},
                    template="FROM_OUTLINE",
                    long_term_memory=long_term_memory,
                    toolkits=toolkits + self.toolkits,
                    tools=tools + self.tools,
                    question=_question,
                    llm=llm or self.llm,
                    **self.model_kwargs
                )
                for block in resp:
                    yield block
        else:
            yield TextBlock("info", f"没有提纲可供扩写")

    async def afrom_outline(self, toolkits=[], tools=[], question:str=None, llm=None, prev_k:int=1000, next_k:int=500, **model_kwargs):
        """
        从工作台中指定的提纲执行扩写任务。

        每次执行`from_outline`指令时，输出的内容将保存到 state 中的 from_outline 属性。
        """
        outline = self.state.outline
        md = self.state.markdown
        _question = question
        if self.state.data:
            _question = "请根据需要调用工具查询真实数据。"

        if outline:
            for doc in outline:
                # 初始化为空的消息列表
                outline_id = doc.metadata['id']
                self.state.from_outline[outline_id] = []

                long_term_memory = self.state.from_outline[outline_id]

                (draft, task) = md.fetch_outline_task(doc, prev_k=prev_k, next_k=next_k)
                yield TextBlock("info", f"执行扩写任务 <{outline_id}>：\n{task}")
                draft_md = f'```markdown\n{draft}\n```'
                task_md = f'```markdown\n{task}\n```'
                async for block in self._awrite(
                    input={"draft": draft_md, "task": task_md},
                    template="FROM_OUTLINE",
                    long_term_memory=long_term_memory,
                    toolkits=toolkits + self.toolkits,
                    tools=tools + self.tools,
                    question=_question,
                    llm=llm or self.llm,
                    **self.model_kwargs
                ):
                    yield block
        else:
            yield TextBlock("info", f"没有提纲可供扩写")


    def _write(self, input: Dict[str, Any], template: str = None, long_term_memory: List[Dict[str, Any]] = None, toolkits: list = [], question: str = None, llm = None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。
        """
        if not question:
            question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

        prompt_template = load_chat_template(template or "OUTLINE")
        system_prompt = prompt_template.format(**input)
        # 构造 system_prompt
        long_term_memory.clear()
        long_term_memory.extend([
            {
                'role': 'system',
                'content': system_prompt
            }
        ])
        self.append_knowledge_to_messages(long_term_memory)
        long_term_memory.extend([
            {
                'role': 'user',
                'content': question
            }
        ])

        # 构造一份短期记忆的拷贝
        short_term_memory = long_term_memory[None:None]

        resp = self._call(llm, long_term_memory, short_term_memory, toolkits, **model_kwargs)
        for block in resp:
            yield block

    async def _awrite(self, input: Dict[str, Any], template: str = None, long_term_memory: List[Dict[str, Any]] = None, toolkits: list = [], question: str = None, llm = None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。
        """
        if not question:
            question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

        prompt_template = load_chat_template(template or "OUTLINE")
        system_prompt = prompt_template.format(**input)
        # 构造 system_prompt
        long_term_memory.clear()
        long_term_memory.extend([
            {
                'role': 'system',
                'content': system_prompt
            }
        ])
        self.append_knowledge_to_messages(long_term_memory)
        long_term_memory.extend([
            {
                'role': 'user',
                'content': question
            }
        ])

        # 构造一份短期记忆的拷贝
        short_term_memory = long_term_memory[None:None]

        async for block in self._acall(llm, long_term_memory, short_term_memory, toolkits, **model_kwargs):
            yield block


    def _call(self, llm, long_term_memory, short_term_memory, toolkits, **model_kwargs):
        # 调用大模型

        to_continue_call_llm = True
        while(to_continue_call_llm):
            to_continue_call_llm = False
            output_text = ""
            tools_call = []

            # 大模型推理
            llm_result = llm(short_term_memory, **model_kwargs)
            for block in (llm_result or []):
                yield block
                if isinstance(block, TextBlock):
                    if block.block_type in ['text', 'chunk', 'front_matter']:
                        output_text += block.text
                    
                    if block.block_type in ['tools_call_chunk']:
                        tools_call.append(json.loads(block.text))
                else:
                    output_text += block.text

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
                            tool_info = [
                                {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [tool]
                                },
                                {
                                    "role": "tool",
                                    "name": tool['function']['name'],
                                    "content": tool_resp
                                }
                            ]
                            short_term_memory.extend(tool_info)
                            long_term_memory.extend(tool_info)
                            to_continue_call_llm = True
            else:
                long_term_memory.extend([{
                    'role': 'assistant',
                    'content': output_text
                }])
                short_term_memory.extend([{
                    'role': 'assistant',
                    'content': output_text
                }])
                # 补充校验的尾缀
                yield create_chk_block(output_text)
            
    async def _acall(self, llm, long_term_memory, short_term_memory, toolkits, **model_kwargs):
        to_continue_call_llm = True
        while(to_continue_call_llm):
            to_continue_call_llm = False
            output_text = ""
            tools_call = []

            # 大模型推理
            if asyncio.iscoroutinefunction(llm):
                llm_result = await llm(short_term_memory, **model_kwargs)
            else:
                llm_result = await asyncio.to_thread(llm, short_term_memory, **model_kwargs)

            for block in (llm_result or []):
                yield block
                if isinstance(block, TextBlock):
                    if block.block_type in ['text', 'chunk', 'front_matter']:
                        output_text += block.text
                    
                    if block.block_type in ['tools_call_chunk']:
                        tools_call.append(json.loads(block.text))
                else:
                    output_text += block.text

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

                            if asyncio.iscoroutinefunction(struct_tool.coroutine):
                                tool_func_result = await struct_tool.coroutine(**args)
                            else:
                                tool_func_result = await asyncio.to_thread(struct_tool.func, **args)

                            for x in tool_func_result:
                                if isinstance(x, TextBlock):
                                    if x.block_type == "tool_resp_final":
                                        tool_resp = x.text
                                    yield x
                                else:
                                    tool_resp += x
                                    yield TextBlock("tool_resp_chunk", x)
                            tool_info = [
                                {
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [tool]
                                },
                                {
                                    "role": "tool",
                                    "name": tool['function']['name'],
                                    "content": tool_resp
                                }
                            ]
                            short_term_memory.extend(tool_info)
                            long_term_memory.extend(tool_info)
                            to_continue_call_llm = True
            else:
                long_term_memory.extend([{
                    'role': 'assistant',
                    'content': output_text
                }])
                short_term_memory.extend([{
                    'role': 'assistant',
                    'content': output_text
                }])
                # 补充校验的尾缀
                yield create_chk_block(output_text)
            

