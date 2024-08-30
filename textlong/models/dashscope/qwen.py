from http import HTTPStatus
from dashscope import Generation
from ...utils import stream_log
from ...message import TextBlock
def qwen(prompt, model="qwen-turbo"):
    """
    messages = [
        {'role':'system','content':'you are a helpful assistant'},
        {'role': 'user','content': '你是谁？'}
        ]

    gen(messages)
    """

    # 转换消息格式
    if isinstance(prompt, str):
        messages = [
            {'role':'system','content':'you are a helpful assistant'},
            {'role': 'user', 'content': prompt}
        ]
    else:
        messages = prompt

    # 调用生成接口
    responses = Generation.call(
        model="qwen-turbo",
        messages=messages,
        result_format='message',
        stream=True,
        incremental_output=True
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
