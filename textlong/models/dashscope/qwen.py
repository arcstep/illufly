from http import HTTPStatus
from dashscope import Generation

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
    full_content = ""

    # 默认使用流输出
    for response in responses:
        if response.status_code == HTTPStatus.OK:
            chunk = response.output.choices[0].message.content
            yield chunk
            full_content += chunk
        else:
            yield ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))
    print(f"Full content:{full_content}")

    # 返回生成的文本
    yield full_content

def qwen_log(prompt, model="qwen-turbo"):
    for chunk in qwen(prompt, model):
        print(chunk, end='')
