from typing import Union, List, Optional
import os
import json

from ..io import TextBlock

from zhipuai import ZhipuAI

def zhipu(
    prompt: Union[str, List[dict]],
    model: str="glm-4-flash",
    api_key: str=None,
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

    client = ZhipuAI(api_key=api_key or os.getenv("ZHIPU_API_KEY"))
    completion = client.chat.completions.create(
        model=model,
        messages=_prompt,
        stream=True,
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
