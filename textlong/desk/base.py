import re
import os
import json
import hashlib
from threading import Thread

from typing import List, Union, Dict, Any
from langchain_core.utils.function_calling import convert_to_openai_tool

from ..config import get_env
from ..io import chk_tail, yield_block
from ..hub import load_chat_template
from ..llm import qwen
from ..llm.tools import create_python_code_tool
from ..utils import compress_text

from .markdown import Markdown, parse_markdown
from .history import History
from .state import State
from ..io import BaseLog, StreamLog

import pandas as pd

class Desk:
    def __init__(self, llm, toolkits: list=[], tools: list=[], k: int=10, logger: BaseLog=None, history: History=None, **model_kwargs):
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
        self.logger = logger or StreamLog()

    def __str__(self):
        return f"Desk(state={self.state})"
    
    def __repr__(self):
        return f"Desk(state={self.state})"
    
    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.state.add_dataset(name, df, desc)
    
    def add_knowledge(self, knowledge: str):
        self.state.add_knowledge(knowledge)
    
    @property
    def tools(self):
        python_code_tool = create_python_code_tool(self.state.data, self.llm, logger=self.logger, **self.model_kwargs)
        return self._tools + [convert_to_openai_tool(python_code_tool)]
    
    @property
    def toolkits(self):
        python_code_tool = create_python_code_tool(self.state.data, self.llm, logger=self.logger, **self.model_kwargs)
        return self._toolkits + [python_code_tool]

    @property
    def output(self):
        return self.state.output

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
    
    def achat(self, question:str, toolkits=[], tools=[], llm=None, new_chat:bool=False, k:int=10, **model_kwargs):
        """
        异步版本的 chat 方法，使用多线程实现非阻塞行为。
        """
        def worker():
            self.chat(question, toolkits, tools, llm, new_chat, k, **model_kwargs)

        thread = Thread(target=worker)
        thread.start()
        return thread

    def chat(self, question:str, toolkits=[], tools=[], llm=None, new_chat:bool=False, k:int=10, **model_kwargs):
        """
        多轮对话时，将对话记录追加到状态数据中的消息列表。
        但如果指定新对话，则首先清空消息列表。

        请注意，执行`chat`指令时，输出不会影响到 output 属性。
        """
        long_term_memory = self.state.messages
        if new_chat:
            long_term_memory.clear()

        # 如果对话从系统消息开始，则保留至少5条消息（以便包括可能出现的 tools 回调）
        final_k = 2 * k if k >= 1 else 1
        if len(long_term_memory) > 0 and long_term_memory[0]['role'] == 'system':
            short_term_memory = long_term_memory[:self.state.reserved_k]
            short_term_memory += long_term_memory[self.state.reserved_k:][-final_k:]
        else:
            short_term_memory = long_term_memory[-final_k:]

        # 将新消息追加到短期记忆中
        new_messages = [{
            'role': 'user',
            'content': question
        }]

        self.append_knowledge_to_messages(long_term_memory)
        long_term_memory.extend(new_messages)

        self.append_knowledge_to_messages(short_term_memory)
        short_term_memory.extend(new_messages)

        self.model_kwargs.update(model_kwargs)
        resp = self._call(
            llm=llm or self.llm,
            long_term_memory=long_term_memory,
            short_term_memory=short_term_memory,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            **model_kwargs
        )
        self.logger.end()
        return resp

    def awrite(self, input:Dict[str, Any], template: str=None, toolkits=[], tools=[], question:str=None, llm=None, **model_kwargs):
        """
        异步版本的 write 方法，使用多线程实现非阻塞行为。
        """
        def worker():
            self.write(input, template, toolkits, tools, question, llm, **model_kwargs)

        thread = Thread(target=worker)
        thread.start()
        return thread

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

        # 针对 write 指令结果对话时，将当前消息列表的长度作为 reserved_k
        self.state.reserved_k = len(long_term_memory)

        # 提取提纲
        md = Markdown(resp[-1]['content'])
        self.state.markdown = md

        self.logger.end()
        return resp

    def afrom_outline(self, toolkits=[], tools=[], question:str=None, llm=None, prev_k:int=1000, next_k:int=500, **model_kwargs):
        """
        异步版本的 from_outline 方法，使用多线程实现非阻塞行为。
        """
        def worker():
            self.from_outline(toolkits, tools, question, llm, prev_k, next_k, **model_kwargs)

        thread = Thread(target=worker)
        thread.start()
        return thread

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
                self.state.from_outline[doc.metadata['id']] = []

                long_term_memory = self.state.from_outline[doc.metadata['id']]

                (draft, task) = md.fetch_outline_task(doc, prev_k=prev_k, next_k=next_k)
                self.logger(yield_block, "info", f"执行扩写任务：\n{task}")
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
        else:
            self.logger(yield_block, "info", f"没有提纲可供扩写")
        
        self.logger.end()

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

        return self._call(llm, long_term_memory, short_term_memory, toolkits, **model_kwargs)

    def _call(self, llm, long_term_memory, short_term_memory, toolkits, **model_kwargs):
        # 调用大模型
        while(True):
            to_continue_call_llm = False
            log = self.logger(llm, short_term_memory, **model_kwargs)
            if log['tools_call']:
                # 如果大模型的结果返回多个工具回调，则要逐个调用完成才能继续下一轮大模型的问调用。
                for index, tool in log['tools_call'].items():
                    for struct_tool in toolkits:
                        if tool['function']['name'] == struct_tool.name:
                            args = json.loads(tool['function']['arguments'])
                            tool_resp = struct_tool.func(**args)
                            self.logger(yield_block, "tool_resp", tool_resp)
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
                    'content': log['output']
                }])
                short_term_memory.extend([{
                    'role': 'assistant',
                    'content': log['output']
                }])
                # 补充校验的尾缀
                self.logger(chk_tail, log['output'])
            
            # 只要不要求继续调用工具，就赶紧跳出循环
            if to_continue_call_llm:
                continue
            else:
                return short_term_memory

