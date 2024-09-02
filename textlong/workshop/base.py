import re
import os
import json
import hashlib
from typing import List, Union, Dict, Any

from ..config import get_env
from ..io import stream_log, chk_tail
from ..hub import load_chat_template

def chat(llm, question:str, messages:List=[], state:Dict={}, toolkits=None, k=10, **model_kwargs):
    """
    基于`messages`中的聊天历史，开始多轮对话。
    在`state`中管理需要一直保留的变量、成果等，例如数据、提纲等。

    Args:
    - llm: 调用模型的函数
    - question: 用户追问的问题
    - messages: 工作台内保留的完整消息列表
    - state: 工作台的状态变量管理
    - k: 保留的历史消息轮数，每轮为2条消息
    - model_kwargs: 模型调用的其他参数
    """
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

    return _call(llm, toolkits, messages, new_messages, **model_kwargs)

def new_chat(messages:List=[]):
    """
    清空聊天历史记录。
    TODO: 后续扩展为支持多版本管理。
    """
    messages.clear()

def write(llm, prompt_id: str=None, input:Dict[str, Any]={}, messages:List=None, state:Dict={}, toolkits=None, question:str=None, **model_kwargs):
    """
    `messages`中的记录将被清空，但会写入新的生成记录。
    """
    if not question:
        question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

    template = load_chat_template(prompt_id)
    system_prompt = template.format(**input)

    # 重置消息列表
    new_chat(messages)
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

    return _call(llm, toolkits, messages, new_messages, **model_kwargs)

def _call(llm, toolkits, messages, new_messages, **model_kwargs):
    """
    调用大模型。

    Args:
    - llm: 调用模型的函数
    - toolkits: 工具包
    - messages: 工作台内保留的完整消息列表
    - new_messages: 对话时代入提示语中的消息列表
    - model_kwargs: 模型调用的其他参数

    """
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