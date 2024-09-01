import re
import os
import json
import hashlib
from typing import List, Union, Dict, Any
from langchain.memory import ConversationBufferWindowMemory
from langchain.memory.chat_memory import BaseChatMemory
from langchain_core.messages.ai import AIMessage, AIMessageChunk
from langchain_core.messages.human import HumanMessage, HumanMessageChunk
from langchain_core.messages.base import BaseMessage, BaseMessageChunk
from langchain_core.messages.chat import ChatMessage, ChatMessageChunk
from langchain_core.messages.function import FunctionMessage, FunctionMessageChunk
from langchain_core.messages.system import SystemMessage, SystemMessageChunk
from langchain_core.messages.tool import ToolMessage, ToolMessageChunk

from ..config import get_env
from ..io import stream_log, chk_tail
from ..hub import create_prompt, load_chat_template

def chat(llm, question:str, messages:List=[], toolkits=None, k=10, is_fake=False, **model_kwargs):
    """
    基于`memory`中的聊天历史，开始多轮对话。

    Args:
    - llm: 调用模型的函数
    - question: 用户追问的问题
    - messages: 记忆存储器
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

def write(llm, prompt_id: str=None, input:Dict[str, Any]={}, messages:List=None, question:str=None, **model_kwargs):
    if not question:
        question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")

    template = load_chat_template(prompt_id)
    system_prompt = template.format(**input)

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

    # 调用大模型
    log = stream_log(llm, messages, **model_kwargs)
    messages.extend([{
        'role': 'assistant',
        'content': log['output']
    }])

    # 补充校验的尾缀
    stream_log(chk_tail, log['output'])
    
    return log['output']

def stream(model_call, prompt_id:str=None, question:str=None, memory:BaseChatMemory=None, input:Dict[str, Any]={}, **model_kwargs):
    """
    stream 实现了大模型调用的逻辑封装，包括：提示语模板、模型和基于追问的记忆管理。

    请注意记忆管理逻辑：如果调用不是制定了quesiton参数来追问，则记忆会被清空。
    这个「奇怪」的设计也可以被当作清空聊天记录的技巧。

    当然，这个设计实际上并不「奇怪」，而是专门为长文档写作的场景考虑而设计。
    当你在生成长文档时，通常并不需要根据聊天历史记录，而是根据模板中要求填写的参数来生成文档；
    相反的，如果你需要针对已经生成的长文档成果来讨论，则可能需要一直保持聊天历史记录。

    在实际使用中，question 可以在第一次写作时就同时提出，也可以在后续追问时提出。

    Args:
    - model_call: 调用的模型函数
    - prompt_id: 提示语模板ID
    - input: 提示语模板的输入参数字典
    - question: 用户追问的问题
    - memory: 记忆存储器
    - model_kwargs: 模型调用的其他参数
    """
    # 构建提示语
    history = get_raw_messages(memory)
    prompt = create_prompt(prompt_id, question, history, **input)

    # 调用大模型
    output_text = stream_log(model_call, prompt, **model_kwargs)

    # 整理记忆
    if memory:
        # 没有指定问题时，则清空记忆
        if not question:
            question = get_env("TEXTLONG_USER_MESSAGE_DEFAULT")
            memory.chat_memory.clear()

        if len(memory.chat_memory.messages) == 0:
            memory.chat_memory.add_message(SystemMessage(prompt[0]["content"]))
            memory.chat_memory.add_message(HumanMessage(prompt[1]["content"]))
        else:
            memory.chat_memory.add_message(HumanMessage(question))

        memory.chat_memory.add_message(AIMessage(output_text))

    # 生成哈希值
    # 移除前后空格以确保唯一性
    trimmed_output_text = output_text.strip()
    hash_object = hashlib.sha256(trimmed_output_text.encode())
    hash_hex = hash_object.hexdigest()  # 获取十六进制哈希值
    # 转换为8位数字哈希值
    hash_code = int(hash_hex, 16) % (10 ** 8)  # 取模运算得到8位数字

    tail = f'>-[END]>> 【{get_env("TEXTLONG_AIGC_INFO_DECLARE")}，{get_env("TEXTLONG_AIGC_INFO_CHK")} {hash_code}】'
    print(tail)
    
    return output_text

def get_raw_messages(memory):
    """
    从记忆对象构造用于大模型调用的消息列表。

    以下是检查合法性的准则：
    1. role 必须是 ["user", "assistant", "system", "function", "plugin", "tool"] 其中之一
    2. 最后一条消息的 role 必须是 ["user", "function", "tool"] 其中之一
    3. 返回时剔除 role 为 system 的消息
    """
    if not memory:
        return []

    # messages = memory.chat_memory.messages
    messages = memory

    string_messages = []
    selected_messages = messages[:2] + messages[2:][-20:]
    for m in selected_messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, ChatMessage):
            role = m.role
        elif isinstance(m, SystemMessage):
            role = "System"
            continue
        else:
            raise ValueError(f"Got unsupported message type: {m}")

        string_messages.append({
            'role': role,
            'content': m.content
        })

    return string_messages