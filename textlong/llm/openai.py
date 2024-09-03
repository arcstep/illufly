from openai import OpenAI
import os

from typing import Union, List, Optional
from langchain.memory import ConversationBufferWindowMemory
from langchain.memory.chat_memory import BaseChatMemory

from http import HTTPStatus
from dashscope import Generation
from ..io import TextBlock

def openai(
    prompt: Union[str, List[dict]],
    model: str="gpt-4o",
    memory: Optional[BaseChatMemory]=None,
    **kwargs
    ):

    completion = OpenAI().chat.completions.create(
        model=model,
        messages=prompt,
        temperature=0.8,
        top_p=0.8,
        stream=True,
        # 可选，配置以后会在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": False}
    )

    for chunk in completion:
        try:
            if len(chunk.choices) == 0:
                print(chunk)
            else:
                content = chunk.choices[0].delta.content
                if content:
                    # yield TextBlock("chunk", content)
                    print(content, end="")
        except BaseException as e:
            print(e)
            print(chunk)
