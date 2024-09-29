✨🦋 [![PyPI version](https://img.shields.io/pypi/v/illufly.svg)](https://pypi.org/project/illufly/)

## illulfy 的设计原则

**1. 简化原则**

作为开发者，在使用通用大模型构建AI应用时，也许你常常会感受到繁琐。<br>
illufly 通常使用内置结构来支持各种场景，包括内置的流失输出，内置的异步调用，内置的多轮记忆，内置的工具回调逻辑等。<br>
这些能力通常没有定制开发的必要。

而使用 illufly 时主要做两件事：一是声明，二是调用。

与大模型官方例子比较时可以进一步感受到。

**2. 鼓励全面支持大模型原厂能力**

实际上 illufly 鼓励使用大模型原厂商的标准，在尽量回避自己定义标准，例如大模型调用时需要录入的消息格式。<br>
请参考[《消息格式》](#消息格式)

## 单轮对话

下面以通义千问的对话模型为例。

### 代码对比

这是一个大模型的 `hello world` 例子。

事实上，`illufly` 有很多简化的特性，但也支持官方的习惯。

**官方示范**


```python
import os
import dashscope

messages = [
    {'role': 'system', 'content': 'You are a helpful assistant.'},
    {'role': 'user', 'content': '你是谁？'}
    ]
response = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=messages,
    result_format='message'
    )
print(response)

```
    {"status_code": 200, "request_id": "f3aea9ce-68a3-9632-87b4-56992dc0fbaa", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "我是来自阿里云的大规模语言模型，我叫通义千问。"}}]}, "usage": {"input_tokens": 22, "output_tokens": 16, "total_tokens": 38}}


**illufly**


```python
import os
from illufly.chat import ChatQwen

# 声明
qwen = ChatQwen(model="qwen-plus", api_key=os.getenv('DASHSCOPE_API_KEY'))

# 调用
qwen([
    {'role': 'system', 'content': 'You are a helpful assistant.'},
    {'role': 'user', 'content': '你是谁？'}
], verbose=True)

```
    我是来自阿里云的大规模语言模型，我叫通义千问。
    
      1s [USAGE] {"input_tokens": 22, "output_tokens": 16, "total_tokens": 38}


    '我是来自阿里云的大规模语言模型，我叫通义千问。'


**极简写法**


```python
from illufly.chat import ChatQwen

# 声明
qwen = ChatQwen(model="qwen-plus")

# 调用
qwen(['You are a helpful assistant.', '你是谁？'])

```
    我是来自阿里云的大规模语言模型，我叫通义千问。
    


    '我是来自阿里云的大规模语言模型，我叫通义千问。'


```python
qwen.memory

```
    [{'role': 'system', 'content': 'You are a helpful assistant.'},
     {'role': 'user', 'content': '你是谁？'},
     {'role': 'assistant', 'content': '我是来自阿里云的大规模语言模型，我叫通义千问。'}]


## 消息格式

illufly 主要使用 python 的原生列表类型来定义消息，并通过语法糖实现快速定义。

大模型所需要的消息列表格式，通常是这样：

### 文本消息


```python
[
    {'role': 'system', 'content': '你是一个小说家。'},
    {'role': 'user', 'content': '帮我创作吧'},
    {'role': 'assistant', 'content': '从前有一个人很坏，他坏死了。\n额，我是他说真的死了。'}
]

```
这有些啰嗦，使用 illufly 可以简化这些工作，然后在使用时被转换为上述标准结构：


```python
from illufly.types import Messages

# 一般情况你不需要直接使用 Messages，但用它确认转换后的消息结构很方便
Messages([
    ('system', '你是一个小说家。'),
    ('user', '帮我创作吧'),
    ('assistant', '从前有一个人很坏，他坏死了。\n额，我是他说真的死了。')
]).to_list()

```
    [{'role': 'system', 'content': '你是一个小说家。'},
     {'role': 'user', 'content': '帮我创作吧'},
     {'role': 'assistant', 'content': '从前有一个人很坏，他坏死了。\n额，我是他说真的死了。'}]


你甚至可以写成这样，转换为标准结构时，illufly 会猜测他们的 role 应该是什么：


```python
Messages([
    '你是一个小说家。',
    '帮我创作吧',
    '从前有一个人很坏，他坏死了。\n额，我是他说真的死了。'
]).to_list()

```
    [{'role': 'system', 'content': '你是一个小说家。'},
     {'role': 'user', 'content': '帮我创作吧'},
     {'role': 'assistant', 'content': '从前有一个人很坏，他坏死了。\n额，我是他说真的死了。'}]


### 提示语模板

你也可以在其中使用模板：


```python
from illufly.types import Template

Messages([
    Template(template_text="你是强有力的AI助手，特别擅长{{skill}}"),
    '帮我创作一首儿歌'
]).to_list(input_vars={"skill": "儿童文学创作"})

```
    [{'role': 'system', 'content': '你是强有力的AI助手，特别擅长儿童文学创作'},
     {'role': 'user', 'content': '帮我创作一首儿歌'}]


或者根据 template_id 使用框架内置的或本地文件中的提示语模板：


```python
from illufly.types import Template

Messages([
    Template("IDEA"),
    '帮我创作一首儿歌'
]).to_list(input_vars={"task": "儿童文学创作"})

```
    [{'role': 'system',
      'content': '你是强大的写作助手。\n\n你必须遵循以下约束来完成任务:\n1. 直接输出你的结果，不要评论，不要啰嗦\n2. 使用markdown格式输出\n\n**你的任务是:**\n儿童文学创作\n'},
     {'role': 'user', 'content': '帮我创作一首儿歌'}]


### 多模态消息

在图片理解、声音理解、视频理解、图片生成等模型中都可能需要上传文件资源，超出了上述纯文本消息格式的表达能力，因此 OpenAI 设计了多模态消息格式，可以支持 `image`、`audio`、`video` 等多种模态格式。但 OpenAI 的标准格式略显繁琐。

**OpenAI兼容的多模态消息格式**


```python
messages=[
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"
                }
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"
                }
            },
            {
                "type": "text",
                "text": "这些是什么"
            }
        ]
    }
]

```
**通义千问的多模态消息格式**

这的确稍微简化了一点。


```python
messages = [
    {
        "role": "user",
        "content": [
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"},
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"},
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/rabbit.png"},
            {"text": "这些是什么?"}
        ]
    }
]

```
**illufly**

illufly 支持直接使用上述任意风格定义多模态消息列表，但也支持自己的简化风格。


```python
messages = [
    (
        "user", 
        [
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg"},
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png"},
            {"image": "https://dashscope.oss-cn-beijing.aliyuncs.com/images/rabbit.png"},
            {"text": "这些是什么?"}
        ]
    )
]

```
使用 illufly 定义好的消息格式可以任意切换为 openai 或 通义千问风格。


```python
Messages(messages).to_list(style="openai_vl")

```
    [{'role': 'user',
      'content': [{'type': 'image_url',
        'image_url': {'url': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg'}},
       {'type': 'image_url',
        'image_url': {'url': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png'}},
       {'type': 'image_url',
        'image_url': {'url': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/rabbit.png'}},
       {'type': 'text', 'text': '这些是什么?'}]}]


```python
Messages(messages).to_list(style="qwen_vl")

```
    [{'role': 'user',
      'content': [{'image': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/dog_and_girl.jpeg'},
       {'image': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/tiger.png'},
       {'image': 'https://dashscope.oss-cn-beijing.aliyuncs.com/images/rabbit.png'},
       {'text': '这些是什么?'}]}]


## 多轮对话

### 代码对比

相比于官方SDK，`illufly` 有内置的多轮对话管理。

**官方例子**


```python
from dashscope import Generation

def get_response(messages):
    response = Generation.call(
        model="qwen-plus",
        messages=messages,
        # 将输出设置为"message"格式
        result_format="message",
    )
    return response

messages = [
    {
        "role": "system",
        "content": """你是一名百炼手机商店的店员，你负责给用户推荐手机。手机有两个参数：屏幕尺寸（包括6.1英寸、6.5英寸、6.7英寸）、分辨率（包括2K、4K）。
        你一次只能向用户提问一个参数。如果用户提供的信息不全，你需要反问他，让他提供没有提供的参数。如果参数收集完成，你要说：我已了解您的购买意向，请稍等。""",
    }
]

assistant_output = "欢迎光临百炼手机商店，您需要购买什么尺寸的手机呢？"
print(f"模型输出：{assistant_output}\n")
while "我已了解您的购买意向" not in assistant_output:
    user_input = input("请输入：")
    # 将用户问题信息添加到messages列表中
    messages.append({"role": "user", "content": user_input})
    assistant_output = get_response(messages).output.choices[0].message.content
    # 将大模型的回复信息添加到messages列表中
    messages.append({"role": "assistant", "content": assistant_output})
    print(f"模型输出：{assistant_output}")
    print("\n")

```
    模型输出：欢迎光临百炼手机商店，您需要购买什么尺寸的手机呢？
    


    请输入： 有什么推荐？


    模型输出：当然可以！为了给您提供更准确的推荐，请问您更倾向于哪种屏幕尺寸呢？是6.1英寸、6.5英寸还是6.7英寸的呢？
    
    


    请输入： 6.1吧


    模型输出：好的，了解。接下来，请问您对屏幕分辨率有偏好吗？您希望是2K还是4K的呢？
    
    


    请输入： 2k


    模型输出：我已了解您的购买意向，请稍等。根据您的选择，我会为您挑选一款6.1英寸且分辨率为2K的手机。
    
    


```python
print(messages)

```
    [{'role': 'system', 'content': '你是一名百炼手机商店的店员，你负责给用户推荐手机。手机有两个参数：屏幕尺寸（包括6.1英寸、6.5英寸、6.7英寸）、分辨率（包括2K、4K）。\n        你一次只能向用户提问一个参数。如果用户提供的信息不全，你需要反问他，让他提供没有提供的参数。如果参数收集完成，你要说：我已了解您的购买意向，请稍等。'}, {'role': 'user', 'content': '有什么推荐？'}, {'role': 'assistant', 'content': '当然可以！为了给您提供更准确的推荐，请问您更倾向于哪种屏幕尺寸呢？是6.1英寸、6.5英寸还是6.7英寸的呢？'}, {'role': 'user', 'content': '6.1吧'}, {'role': 'assistant', 'content': '好的，了解。接下来，请问您对屏幕分辨率有偏好吗？您希望是2K还是4K的呢？'}, {'role': 'user', 'content': '2k'}, {'role': 'assistant', 'content': '我已了解您的购买意向，请稍等。根据您的选择，我会为您挑选一款6.1英寸且分辨率为2K的手机。'}]


**illufly**


```python
from illufly.chat import ChatQwen

# 声明
qwen = ChatQwen(
    model="qwen-plus",
    memory="""你是一名百炼手机商店的店员，你负责给用户推荐手机。
        手机有两个参数：屏幕尺寸（包括6.1英寸、6.5英寸、6.7英寸）、分辨率（包括2K、4K）。
        你一次只能向用户提问一个参数。如果用户提供的信息不全，你需要反问他，让他提供没有提供的参数。
        如果参数收集完成，你要说：我已了解您的购买意向，请稍等。"""
    )

assistant_output = "欢迎光临百炼手机商店，您需要购买什么尺寸的手机呢？"
print(f"模型输出：{assistant_output}\n")
while "我已了解您的购买意向" not in assistant_output:
    user_input = input("请输入：")

    # 调用
    assistant_output = qwen(user_input)

```
    模型输出：欢迎光临百炼手机商店，您需要购买什么尺寸的手机呢？
    


    请输入： 6寸？


    我们当前没有6英寸的手机屏幕尺寸，不过我们有6.1英寸、6.5英寸以及6.7英寸的手机。您更倾向于哪种尺寸呢？
    


    请输入： 6.5


    好的，您喜欢的是6.5英寸的手机。接下来，请问您对手机的分辨率有要求吗？比如2K或4K？
    


    请输入： 4K吧


    好的，您选择的是6.5英寸和4K分辨率的手机。我已了解您的购买意向，请稍等。
    


```python
qwen.memory

```
    [{'role': 'system',
      'content': '你是一名百炼手机商店的店员，你负责给用户推荐手机。\n        手机有两个参数：屏幕尺寸（包括6.1英寸、6.5英寸、6.7英寸）、分辨率（包括2K、4K）。\n        你一次只能向用户提问一个参数。如果用户提供的信息不全，你需要反问他，让他提供没有提供的参数。\n        如果参数收集完成，你要说：我已了解您的购买意向，请稍等。'},
     {'role': 'user', 'content': '6寸？'},
     {'role': 'assistant',
      'content': '我们当前没有6英寸的手机屏幕尺寸，不过我们有6.1英寸、6.5英寸以及6.7英寸的手机。您更倾向于哪种尺寸呢？'},
     {'role': 'user', 'content': '6.5'},
     {'role': 'assistant',
      'content': '好的，您喜欢的是6.5英寸的手机。接下来，请问您对手机的分辨率有要求吗？比如2K或4K？'},
     {'role': 'user', 'content': '4K吧'},
     {'role': 'assistant', 'content': '好的，您选择的是6.5英寸和4K分辨率的手机。我已了解您的购买意向，请稍等。'}]


## 工具回调

### 代码对比

相比于官方SDK，`illufly` 天然支持工具回调，而且简化了工具定义的方法。

在下面 `illufly` 的例子中除了工具回调，还支持流输出和多轮对话。

**官方例子**


```python
from dashscope import Generation
from datetime import datetime
import random
import json

# 定义工具列表，模型在选择使用哪个工具时会参考工具的name和description
tools = [
    # 工具1 获取当前时刻的时间
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "当你想知道现在的时间时非常有用。",
            "parameters": {}  # 因为获取当前时间无需输入参数，因此parameters为空字典
        }
    },  
    # 工具2 获取指定城市的天气
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "当你想查询指定城市的天气时非常有用。",
            "parameters": {  
                # 查询天气时需要提供位置，因此参数设置为location
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市或县区，比如北京市、杭州市、余杭区等。"
                    }
                }
            },
            "required": [
                "location"
            ]
        }
    }
]

# 模拟天气查询工具。返回结果示例：“北京今天是晴天。”
def get_current_weather(location):
    return f"{location}今天是晴天。 "

# 查询当前时间的工具。返回结果示例：“当前时间：2024-04-15 17:15:18。“
def get_current_time():
    # 获取当前日期和时间
    current_datetime = datetime.now()
    # 格式化当前日期和时间
    formatted_time = current_datetime.strftime('%Y-%m-%d %H:%M:%S')
    # 返回格式化后的当前时间
    return f"当前时间：{formatted_time}。"

# 封装模型响应函数
def get_response(messages):
    response = Generation.call(
        model='qwen-plus',
        messages=messages,
        tools=tools,
        seed=random.randint(1, 10000),  # 设置随机数种子seed，如果没有设置，则随机数种子默认为1234
        result_format='message'  # 将输出设置为message形式
    )
    return response

def call_with_messages():
    print('\n')
    messages = [
            {
                "content": input('请输入：'),  # 提问示例："现在几点了？" "一个小时后几点" "北京天气如何？"
                "role": "user"
            }
    ]
    
    # 模型的第一轮调用
    first_response = get_response(messages)
    assistant_output = first_response.output.choices[0].message
    print(f"\n大模型第一轮输出信息：{first_response}\n")
    messages.append(assistant_output)
    if 'tool_calls' not in assistant_output:  # 如果模型判断无需调用工具，则将assistant的回复直接打印出来，无需进行模型的第二轮调用
        print(f"最终答案：{assistant_output.content}")
        return
    # 如果模型选择的工具是get_current_weather
    elif assistant_output.tool_calls[0]['function']['name'] == 'get_current_weather':
        tool_info = {"name": "get_current_weather", "role":"tool"}
        location = json.loads(assistant_output.tool_calls[0]['function']['arguments'])['location']
        tool_info['content'] = get_current_weather(location)
    # 如果模型选择的工具是get_current_time
    elif assistant_output.tool_calls[0]['function']['name'] == 'get_current_time':
        tool_info = {"name": "get_current_time", "role":"tool"}
        tool_info['content'] = get_current_time()
    print(f"工具输出信息：{tool_info['content']}\n")
    messages.append(tool_info)

    # 模型的第二轮调用，对工具的输出进行总结
    second_response = get_response(messages)
    print(f"大模型第二轮输出信息：{second_response}\n")
    print(f"最终答案：{second_response.output.choices[0].message['content']}")

call_with_messages()

```
    
    


    请输入： 今天可以晒被子不？


    
    大模型第一轮输出信息：{"status_code": 200, "request_id": "c9d445d9-477b-9467-86dd-6d9fb5b3b0bd", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_current_weather", "arguments": "{\"location\": \"杭州市\"}"}, "index": 0, "id": "call_bdab8c159286438a8a37a5", "type": "function"}]}}]}, "usage": {"input_tokens": 222, "output_tokens": 18, "total_tokens": 240}}
    
    工具输出信息：杭州市今天是晴天。 
    
    大模型第二轮输出信息：{"status_code": 200, "request_id": "647a0e02-1e46-9410-8f2e-14fcfbea4f76", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "今天杭州市是晴天，所以可以去晒被子哦！"}}]}, "usage": {"input_tokens": 255, "output_tokens": 16, "total_tokens": 271}}
    
    最终答案：今天杭州市是晴天，所以可以去晒被子哦！


**illufly**


```python
import random
from datetime import datetime
from illufly.chat import ChatQwen

# 声明
def get_current_weather(location: str):
    """当你想查询指定城市的天气时非常有用。"""
    return f"{location}今天是晴天。 "

# 声明
def get_current_time():
    """当你想知道现在的时间时非常有用。"""
    # 获取当前日期和时间
    current_datetime = datetime.now()
    # 格式化当前日期和时间
    formatted_time = current_datetime.strftime('%Y-%m-%d %H:%M:%S')
    # 返回格式化后的当前时间
    return f"当前时间：{formatted_time}。"

# 声明
qwen = ChatQwen(
    model="qwen-plus",
    seed=random.randint(1, 10000),
    tools=[get_current_weather, get_current_time]
)

# 调用
qwen([{'role': 'user', 'content': input('请输入：')}], new_chat=True)

```
    请输入： 天气如何


    Beijing今天是晴天。 
    
    北京今天是晴天。
    


    '北京今天是晴天。'


**工具回调之后的连续多轮对话：**


```python
qwen("现在几点了？")

```
    当前时间：2024-09-28 15:27:51。
    
    现在的时间是2024年9月28日15点27分51秒。
    


    '现在的时间是2024年9月28日15点27分51秒。'


```python
qwen("我之前问过哪里的天气?")

```
    您之前询问了北京的天气。
    


    '您之前询问了北京的天气。'


## 流式输出

### 代码对比

相比于官方SDK，`illufly` 天然支持流式输出，但用起来非常简洁。<br>
实际上在 `ChatQwen` 内部修改了 `result_format='message'`、`stream=True`和`incremental_output=True` 等参数的默认值。

**官方例子**


```python
from http import HTTPStatus
from dashscope import Generation


def call_with_stream():
    messages = [
        {'role':'system','content':'you are a helpful assistant'},
        {'role': 'user','content': '你是谁？'}
        ]
    responses = Generation.call(
        model="qwen-plus",
        messages=messages,
        # 设置输出为'message'格式
        result_format='message',
        # 设置输出方式为流式输出
        stream=True,
        # 增量式流式输出
        incremental_output=True
        )
    full_content = ""
    for response in responses:
        if response.status_code == HTTPStatus.OK:
            print(response)
            full_content += response.output.choices[0].message.content
        else:
            print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                response.request_id, response.status_code,
                response.code, response.message
            ))
    print(f"Full content:{full_content}")

call_with_stream()

```
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "我是"}}]}, "usage": {"input_tokens": 21, "output_tokens": 1, "total_tokens": 22}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "来自"}}]}, "usage": {"input_tokens": 21, "output_tokens": 2, "total_tokens": 23}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "阿里"}}]}, "usage": {"input_tokens": 21, "output_tokens": 3, "total_tokens": 24}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "云"}}]}, "usage": {"input_tokens": 21, "output_tokens": 4, "total_tokens": 25}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "的大规模语言模型"}}]}, "usage": {"input_tokens": 21, "output_tokens": 8, "total_tokens": 29}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "，我叫通"}}]}, "usage": {"input_tokens": 21, "output_tokens": 12, "total_tokens": 33}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "null", "message": {"role": "assistant", "content": "义千问。"}}]}, "usage": {"input_tokens": 21, "output_tokens": 16, "total_tokens": 37}}
    {"status_code": 200, "request_id": "8b2df512-aee6-9cc8-adc6-6c75f7f10815", "code": "", "message": "", "output": {"text": null, "finish_reason": null, "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": ""}}]}, "usage": {"input_tokens": 21, "output_tokens": 16, "total_tokens": 37}}
    Full content:我是来自阿里云的大规模语言模型，我叫通义千问。


**illufly**


```python
from illufly.chat import ChatQwen

# 声明
qwen = ChatQwen(model="qwen-plus")

# 调用
qwen([
    {'role': 'system', 'content': 'You are a helpful assistant'},
    {'role': 'user', 'content': '你是谁？'}
], verbose=True, new_chat=True)

```
    我是来自阿里云的大规模语言模型，我叫通义千问。
    
      1s [USAGE] {"input_tokens": 21, "output_tokens": 16, "total_tokens": 37}


    '我是来自阿里云的大规模语言模型，我叫通义千问。'


## 知识管理

## RAG 检索

## 记忆优化

## 多智能体
