import re
import os
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
from ..utils import stream_log
from ..hub import create_prompt
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
            memory.chat_memory.add_message(SystemMessage(prompt[1]["content"]))
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
    从记忆对象中的 Message 对象列表构造原始的消息列表。

    以下是生成的准则：
    Role must be in ["user", "assistant", "system", "function", "plugin", "tool"] 
    the role in last message must be in ["user", "function", "tool"]
    """
    if not memory:
        return []

    messages = memory.chat_memory.messages
    
    string_messages = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = "user"
        elif isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, SystemMessage):
            role = "System"
        elif isinstance(m, ChatMessage):
            role = m.role
        else:
            raise ValueError(f"Got unsupported message type: {m}")
        string_messages.append({
            'role': role,
            'content': m.content
        })

    return string_messages