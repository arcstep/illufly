# ✨🦋 illufly

[![PyPI version](https://img.shields.io/pypi/v/illufly.svg)](https://pypi.org/project/illufly/)

`illufly` 是 `illution butterfly` 的缩写，中文为"幻蝶"。

**illufly** 的目标是快速构建多智能体的对话和写作场景。

## 详细文档导航

* [illufly 概览](https://github.com/arcstep/illufly/wiki/Home)

**入门指南**
* [安装配置指南](https://github.com/arcstep/illufly/wiki/安装指南)
* [必读的概念解释](https://github.com/arcstep/illufly/wiki/概念)
* [开箱即用的流输出](https://github.com/arcstep/illufly/wiki/流输出)
* [大模型支持](https://github.com/arcstep/illufly/wiki/模型列表)
* [使用检索增强（RAG）](https://github.com/arcstep/illufly/wiki/RAG)

**实践案例**
* [连续对话案例](https://github.com/arcstep/illufly/wiki/对话)
* [长文写作案例](https://github.com/arcstep/illufly/wiki/长文写作)
* [多智能体协作案例](https://github.com/arcstep/illufly/wiki/多智能体)

**高级主题**
* [illufly 的设计理念](https://github.com/arcstep/illufly/wiki/设计理念)
* [illufly 的工作流设计](https://github.com/arcstep/illufly/wiki/工作流)
* [illufly 的推理模式实现](https://github.com/arcstep/illufly/wiki/推理模式)
* [自定义提示语模板](https://github.com/arcstep/illufly/wiki/提示语模板)
* [自定义大模型](https://github.com/arcstep/illufly/wiki/自定义大模型)


## 快速体验

### 安装 `illufly` 包

```sh
pip install illufly
```

#### 推荐使用 `dotenv` 管理环境变量

将`APIKEY`和项目配置保存到`.env`文件，再加载到进程的环境变量中，这是很好的实践策略。

```
## OpenAI 兼容的配置
OPENAI_API_KEY="你的API_KEY"
OPENAI_BASE_URL="你的BASE_URL"

## 阿里云的配置
DASHSCOPE_API_KEY="你的API_KEY"

## 智谱AI的配置
ZHIPUAI_API_KEY="你的API_KEY"
```

在 Python 代码中，使用以下代码片段来加载`.env`文件中的环境变量：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

### 使用示例

#### 创建对话应用

使用极简的代码，就可以构建基于通义千问大模型的对话应用。

下面的代码中使用了流式输出，在执行代码的环境中可以看到：输出是一个字、个词蹦出来的。

```python
from illufly.chat import ChatQwen

# 要使用通义千问，需要先安装 `dashscope` 包
# 并配置好相应的 DASHSCOPE_API_KEY
qwen = ChatQwen()
qwen("你能帮我写一首关于兔子做梦的四句儿歌?")
```

生成结果：
```md
小白兔，梦中跳，  
胡萝卜，满天飘。  
月亮船，带它逛，  
醒来笑，梦真妙。
```

#### 创建连续对话

`ChatQwen`是一个基于通义千问的对话模型。

所有智能体对象都已经封装了多轮对话、工具回调、知识增强等能力。

请看连续对话的例子：

```python
from illufly.chat import ChatQwen

# 简单的系统提示语可以在智能体定义时声明，帮助确定角色、任务等
qwen = ChatQwen(memory="你是一个专门写儿歌的作家，请根据我的提示写作。")
qwen("来一首关于兔子的，四句")
```

生成结果：
```md
小白兔，蹦蹦跳，  
耳朵长，尾巴小。  
爱吃萝卜和青菜，  
快乐生活在林梢。
```

连续提问，它依然懂你：
```python
qwen("换成两条小鱼")
```

生成结果：
```md
两条��鱼，游啊游，  
水中穿梭，乐悠悠。  
摇摇尾巴，吐泡泡，  
大海深处是故乡。
```

`illufly` 智能体对象是有记忆的，使用`qwen.memory`查看：

```python
[{'role': 'system', 'content': '你是一个专门写儿歌的作家，请根据我的提示写作。'},
 {'role': 'user', 'content': '来一首关于兔子的，四句'},
 {'role': 'assistant',
  'content': '小白兔，蹦蹦跳，  \n耳朵长，尾巴小。  \n爱吃萝卜和青菜，  \n快乐生活在林梢。'},
 {'role': 'user', 'content': '换成两条小鱼'},
 {'role': 'assistant',
  'content': '两条小鱼，游啊游，  \n水中穿梭乐悠悠。  \n摇摇尾巴，吐泡泡，  \n大海深处是故乡。'}]
```

#### 使用工具回调

要让`illufly`智能体支持工具回调，只需要提供`tools`参数。

以下示例是定义工具和使用工具的过程：
```python
from illufly.chat import ChatQwen
from types import ToolAgent

def get_current_weather(location: str=None):
    """获取城市的天气情况"""
    return f"{location}今天是晴天。"

q = ChatQwen(tools=[ToolAgent(get_current_weather)])
q("今天广州可以晒被子吗？")
```

生成结果：

```md
广州今天是晴天。 

今天广州是晴天，非常适合晒被子。可以放心地把被子拿出来晾晒。
```

上面的结果中，第一句是工具回调输出的结果，第二句是工具回调后大模型再次生成的流长文本。

你也可以通过设置`verbose=True`来查看工具调用详情：

```python
q("今天广州可以晒被子吗？", verbose=True)
```

生成结果：

```md
[TOOLS_CALL_CHUNK] {"index": 0, "id": "call_8f5d146a77b24d9c97b7ec", "type": "function", "function": {"name": "get_current_weather", "arguments": ""}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {"arguments": "{\"location\": \""}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {"arguments": "广州\"}"}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {}}
[TOOLS_CALL_FINAL] {"0": {"index": 0, "id": "call_8f5d146a77b24d9c97b7ec", "type": "function", "function": {"name": "get_current_weather", "arguments": "{\"location\": \"广州\"}"}}}
广州今天是晴天。 

今天广州是晴天，非常适合晒被子。
```

生成的结果中，增加的`[TOOLS_CALL_CHUNK]...`部分，是大模型第一次推理得出的工具和参数要求，紧接着是工具回调的结果，最后是工具回调后大模型再次合成后的文本。

#### 智能体团队：执行管道

将前面用过的智能体连接起来，就可以形成多智能体团队。

`Pipe` 对象会把多个智能体对象组织起来，分工协作，共同完成任务，使用方法也与普通智能体类似。

```python
from illufly.chat import ChatQwen, Pipe

pipe = Pipe(
    ChatQwen(memory="我是一个儿童作家，擅长写儿歌。"),
    ChatQwen(memory="请你帮我评价文章特色，两句话即可"),
    ChatQwen(memory="请针对我的写作成果打一个分数，给出一句话的打分点，最终给出1分至5分")
)

pipe("你能帮我写一首关于兔子做梦的？四句即可。")
```

生成结果：

```md
[AGENT] >>> Node 1: 我是一个儿童作家，擅长写儿歌。

> 小白兔，梦中跳，月亮船上摇啊摇。
> 胡萝卜，变成桥，梦里世界真奇妙。

[AGENT] >>> Node 2: 请你帮我评价文章特色，两句话即可

> 这首短文充满了童趣和想象力，通过"小白兔在月亮船上摇晃"和"胡萝卜变成桥"的奇幻意象，展现了梦境的奇妙与无尽创意，语言简洁，富有诗意，非常适合儿童阅读，激发他们的想象空间。

[AGENT] >>> Node 3: 请针对我的写作成果打一个分数，给出一句话的打分点，最终给出1分至5分

> 4分。打分点在于作品成功营造了富有童趣和想象力的氛围，语言表达既简洁又有诗意，非常适合儿童阅读，但在内容深度或情节构建上还有提升空间。
```

加入到 `Pipe` 中的智能体对象，都可以使用自己的大模型、提示语、工具箱。其协作过程就像流水线，前一个智能体的输出，直接作为下一个智能体的输入。这是多智能体协作方式的一种，称为`流水线协作`。

`illufly` 中还支持其他协作方式，如`提纲扩写`、`讨论`等。

