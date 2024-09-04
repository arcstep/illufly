import re
import os
import json
import hashlib
from typing import List, Union, Dict, Any

from ..config import get_env
from ..io import stream_log, chk_tail, yield_block
from ..hub import load_chat_template
from ..llm import qwen
from .markdown import Markdown
from .history import History
from .state import State

class Desk:
    def __init__(self, llm, toolkits: list=None, k: int=10, history: History=None, **model_kwargs):
        """
        Args:
        - llm: 调用模型的函数
        - toolkits: 智能体回调工具包
        - k: 保留的历史消息轮数，每轮包括问和答共2条消息
        - history: 对话涉及的大模型调用历史记录
        """

        self.llm = llm
        self.toolkits = toolkits
        self.history = history
        self.k = k
        self.model_kwargs = model_kwargs

        # 
        self.state = State()

    def chat(self, question:str, toolkits=None, llm=None, new_chat:bool=False, k:int=10, **model_kwargs):
        """
        多轮对话时，将对话记录追加到状态数据中的消息列表。
        但如果指定新对话，则首先清空消息列表。
        """
        if new_chat:
            self.state.messages.clear()
        
        self.model_kwargs.update(model_kwargs)
        _chat(
            question,
            messages=self.state.messages,
            toolkits=toolkits or self.toolkits,
            llm=llm or self.llm,
            k=k or self.k,
            **self.model_kwargs
        )

    def write(self, input:Dict[str, Any], template: str=None, toolkits=None, question:str=None, llm=None, **model_kwargs):
        """
        执行单轮写作任务时，首先清空消息列表。
        """
        if not question:
            question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

        prompt_template = load_chat_template(template or "OUTLINE")
        system_prompt = prompt_template.format(**input)

        messages = self.state.messages
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

        # 提取输出
        self.model_kwargs.update(model_kwargs)
        resp = _call(
            llm or self.llm,
            messages,
            new_messages,
            toolkits or self.toolkits,
            **self.model_kwargs
        )

        # 提取提纲
        md = Markdown(resp)
        outline = md.get_outline()

        # 仅当写作任务输出了提纲时，才将更新工作台的提纲信息
        if outline:
            self.state.output = md
            self.state.outline = outline
            self.state.from_outline = {}

        return resp

def _chat(question:str, messages:Dict[str, Any]=None, toolkits=None, llm=None, k:int=10, **model_kwargs):
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
            return log['output']