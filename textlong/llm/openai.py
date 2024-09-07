from openai import OpenAI
import os
import json

from typing import Union, List, Optional
from langchain.memory import ConversationBufferWindowMemory
from langchain.memory.chat_memory import BaseChatMemory

from http import HTTPStatus
from dashscope import Generation
from ..io import TextBlock

def openai(
    prompt: Union[str, List[dict]],
    model: str="gpt-3.5-turbo",
    memory: Optional[BaseChatMemory]=None,
    **kwargs
    ):
    _prompt = prompt
    if isinstance(prompt, str):
        _prompt = [
            {
                "role": "user",
                "content": prompt
            }
        ]

    completion = OpenAI().chat.completions.create(
        model=model,
        messages=_prompt,
        stream=True,
        # temperature=0.8,
        # top_p=0.8,
        # 可选，配置以后会在流式输出的最后一行展示token使用信息
        # stream_options={"include_usage": True},
        **kwargs
    )

    for response in completion:
        if response.choices:
            ai_output = response.choices[0].delta
            if ai_output.tool_calls:
                for func in ai_output.tool_calls:
                    func_json = {
                        "index": func.index or 0,
                        "function": {
                            "id": func.id or "",
                            "type": func.type or "function",
                            "name": func.function.name,
                            "arguments": func.function.arguments
                        }
                    }
                    yield TextBlock("tools_call", json.dumps(func_json, ensure_ascii=False))
            else:
                content = ai_output.content
                if content:
                    yield TextBlock("chunk", content)
