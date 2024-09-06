import re
import os
import json
import hashlib
import copy
from typing import List, Union, Dict, Any

from ..config import get_env
from ..io import stream_log, chk_tail, yield_block
from ..hub import load_chat_template
from ..llm import qwen
from .markdown import Markdown, parse_markdown
from .history import History
from .state import State

from ..llm.tools import create_python_code_tool, convert_to_openai_tool

class Desk:
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
    
    def load_data(self, data: Dict[str, Any]):
        self.state.data.update(data)
    
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
        if self.state.outline:
            md = copy.deepcopy(self.state.markdown)
            for doc in self.state.outline:
                if doc.metadata['id'] in self.state.from_outline:
                    from_outline_text = self.state.from_outline[doc.metadata['id']][-1]['content']
                    md.replace_documents(doc, doc, from_outline_text)
            return md.text
        else:
            return self.state.markdown.text

    def chat(self, question:str, toolkits=[], tools=[], llm=None, new_chat:bool=False, k:int=10, **model_kwargs):
        """
        多轮对话时，将对话记录追加到状态数据中的消息列表。
        但如果指定新对话，则首先清空消息列表。
        """
        if new_chat:
            self.state.messages.clear()
        
        self.model_kwargs.update(model_kwargs)
        return _chat(
            question,
            messages=self.state.messages,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            llm=llm or self.llm,
            k=k or self.k,
            **self.model_kwargs
        )

    def write(self, input:Dict[str, Any], template: str=None, toolkits=[], tools=[], question:str=None, llm=None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。
        """
        
        self.model_kwargs.update(model_kwargs)
        resp = _write(
            input,
            template=template,
            messages=self.state.messages,
            toolkits=toolkits + self.toolkits,
            tools=tools + self.tools,
            question=question,
            llm=llm or self.llm,
            **self.model_kwargs
        )

        # 提取提纲
        md = Markdown(resp[-1]['content'])
        self.state.markdown = md

        return resp

    def from_outline(self, toolkits=[], tools=[], llm=None, **model_kwargs):
        """
        从工作台中指定的提纲执行扩写任务。
        """
        outline = self.state.outline
        md = self.state.markdown

        if md:
            outline = md.get_outline()
            for doc in outline:
                # 初始化为空的消息列表
                self.state.from_outline[doc.metadata['id']] = []
                new_messages = self.state.from_outline[doc.metadata['id']]

                (draft, task) = md.fetch_outline_task(doc)
                stream_log(yield_block, "info", f"执行扩写任务：\n{task}")
                resp = _write(
                    input={"draft": draft, "task": task},
                    template="FROM_OUTLINE",
                    messages=new_messages,
                    toolkits=toolkits + self.toolkits,
                    tools=tools + self.tools,
                    llm=llm or self.llm,
                    **self.model_kwargs
                )

def _write(input:Dict[str, Any], template: str=None, messages:Dict[str, Any]=None, toolkits=[], question:str=None, llm=None, **model_kwargs):
    """
    执行单轮写作任务时，首先清空消息列表。
    """
    if not question:
        question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

    prompt_template = load_chat_template(template or "OUTLINE")
    system_prompt = prompt_template.format(**input)

    # 重置消息列表
    messages.clear()
    # 构造 system_prompt
    messages.extend([
        {
            'role': 'system',
            'content': system_prompt
        },
        {
            'role': 'user',
            'content': question
        }
    ])

    # 构造一份短期记忆的拷贝
    new_messages = messages[None:None]

    return _call(llm, messages, new_messages, toolkits, **model_kwargs)

def _chat(question:str, messages:Dict[str, Any]=None, toolkits=[], llm=None, k:int=10, **model_kwargs):
    # 将问题增加到消息列表的最后
    messages.extend([{
        'role': 'user',
        'content': question
    }])

    # 如果第1条消息为 system 类型，就永远保留前3条消息和最后的k-1轮，否则就保留最后的k轮
    if messages[0]['role'] == 'system':
        final_k = 2*k-3 if k >= 2 else 1
        new_messages = messages[:3] + messages[3:][-final_k:]
    else:
        final_k = 2*k-1 if k >= 1 else 1
        new_messages = messages[-final_k:]

    return _call(llm, messages, new_messages, toolkits, **model_kwargs)

def _call(llm, messages, new_messages, toolkits, **model_kwargs):
    # 调用大模型
    while(True):
        to_continue_call_llm = False
        log = stream_log(llm, new_messages, **model_kwargs)

        if log['tools_call']:
            # 如果大模型的结果返回多个工具回调，则要逐个调用完成才能继续下一轮大模型的访问调用。
            for index, tool in log['tools_call'].items():
                for struct_tool in toolkits:
                    if tool['function']['name'] == struct_tool.name:
                        args = json.loads(tool['function']['arguments'])
                        tool_resp = struct_tool.func(**args)
                        stream_log(yield_block, "tool_resp", tool_resp)
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
                        new_messages.extend(tool_info)
                        messages.extend(tool_info)
                        to_continue_call_llm = True
        else:
            messages.extend([{
                'role': 'assistant',
                'content': log['output']
            }])
            # 补充校验的尾缀
            stream_log(chk_tail, log['output'])
        
        # 只要不要求继续调用工具，就赶紧跳出循环
        if to_continue_call_llm:
            continue
        else:
            return messages