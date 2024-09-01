from typing import Union, List, Optional
from ..io import TextBlock

def fake_llm(
    prompt: Union[str, List[dict]],
    model: str="fake",
    **kwargs):
    """
    Args:
    - prompt 支持字符串提示语或消息列表。

    Example:
        messages = [
            {'role':'system','content':'you are a helpful assistant'},
            {'role': 'user','content': '你是谁？'}
        ]

        stream(qwen, messages)
    """

    # 转换消息格式
    if isinstance(prompt, str):
        yield TextBlock("chunk", prompt)
    else:
        for message in prompt:
            yield TextBlock("info", f'{message["role"]}: {message["content"]}')

    # 调用生成接口
    responses = ["这", "是", "一个", "模拟", "调用", "!"]

    # 默认使用流输出
    full_content = ""
    for content in responses:
        yield TextBlock("chunk", content)
        full_content += content
