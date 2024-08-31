from typing import Union, List, Optional
from langchain.memory import ConversationBufferWindowMemory
from langchain.memory.chat_memory import BaseChatMemory

from http import HTTPStatus
from dashscope import Generation
from ...utils import stream_log
from ...message import TextBlock

def qwen(
    prompt: Union[str, List[dict]],
    model: str="qwen-turbo",
    memory: Optional[BaseChatMemory]=None,
    **kwargs):
    """
    Args:
    - prompt 支持字符串提示语或消息列表。

    Example:
        messages = [
            {'role':'system','content':'you are a helpful assistant'},
            {'role': 'user','content': '你是谁？'}
        ]

        stream_log(qwen, messages)
    """

    # 转换消息格式
    _messages = None
    _prompt = None
    if isinstance(prompt, str):
        _prompt = prompt
    else:
        _messages = prompt

    # 调用生成接口
    responses = Generation.call(
        model="qwen-turbo",
        messages=_messages,
        prompt=_prompt,
        result_format='message',
        stream=True,
        incremental_output=True,
        **kwargs
        )

    # 默认使用流输出
    full_content = ""
    for response in responses:
        if response.status_code == HTTPStatus.OK:
            content = response.output.choices[0].message.content
            yield TextBlock("chunk", content)
            full_content += content
        else:
            yield TextBlock("info", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            )))

    yield TextBlock("final", full_content)
