# 🦋✨ illufly

[![PyPI version](https://img.shields.io/pypi/v/illufly.svg)](https://pypi.org/project/illufly/)

**illufly** 的目标是围绕对话和写作场景，提供多智能体的快速交付框架。

`illufly` 是 `illution butterfly` 的缩写，中文为“幻蝶”。

# 《illufly 使用指南》

## 1. 模型支持

目前，框架主要支持以下大模型接口：
- OpenAI 或协议兼容的模型
- 阿里云模型积灵和百炼大模型，包括通义千问通用模型等
- 智谱AI的GLM4系列通用模型

## 2 使用 dotenv 管理环境变量

将 APIKEY 和项目配置保存到`.env`文件，再加载到进程的环境变量中，这是很好的实践策略。

这需要使用 dotenv 包，它可以帮助我们管理项目中的环境变量。

创建和配置`.env`文件，你需要在你项目的根目录下创建一个名为`.env`的文件（注意，文件名以点开始）。在这个文件中，你可以定义你的环境变量，例如：

```
## OpenAI 兼容的配置
OPENAI_API_KEY="你的API_KEY"
OPENAI_BASE_URL="你的BASE_URL"

## 阿里云的配置
DASHSCOPE_API_KEY="你的API_KEY"

## 智谱AI的配置
ZHIPUAI_API_KEY="你的API_KEY"
```

为此，你可能需要先安装 python-dotenv 包：

```bash
pip install python-dotenv
```

然后在 Python 代码中，使用以下代码片段来加载`.env`文件中的环境变量：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

## 3 illufly 的安装与加载

### 3.1 安装 illufly 包

在 Python 中安装 illufly 包非常简单，以下命令会尝试安装最新版本的 illufly：

```sh
pip install illufly
```

为了确保安装的是最新版本，可以在命令中添加`--upgrade`选项，如下：

```sh
pip install --upgrade illufly
```

## 4 使用示例

### 4.1 创建对话应用

下面使用通义千问智能体，生成一首儿歌。
```python
from illufly.agent import ChatQwen
from illufly.io import log

qwen = ChatQwen()
log(qwen, "你能帮我写一首关于兔子做梦的四句儿歌?")
```

生成结果：
```md
小白兔，梦中跳，  
胡萝卜，满天飘。  
月亮船，带它逛，  
醒来笑，梦真妙。
```

### 4.2 创建连续对话

```python
from illufly.agent import ChatQwen
from illufly.io import log

qwen = ChatQwen(prompt="你是一个专门写儿歌的作家，请根据我的提示写作。")
log(qwen, "来一首关于兔子的，四句")
```

生成结果：
```md
小白兔，蹦蹦跳，  
耳朵长，尾巴小。  
爱吃萝卜和青菜，  
快乐生活在林梢。
```

你可以使用连续对话模式继续提问：
```python
log(qwen, "换成两条小鱼")
qwen.memory
```

生成结果：
```md
两条小鱼，游啊游，  
水中穿梭，乐悠悠。  
摇摇尾巴，吐泡泡，  
大海深处是故乡。
```

```python
[{'role': 'system', 'content': '你是一个专门写儿歌的作家，请根据我的提示写作。'},
 {'role': 'user', 'content': '来一首关于兔子的，四句'},
 {'role': 'assistant',
  'content': '小白兔，蹦蹦跳，  \n耳朵长，尾巴小。  \n爱吃萝卜和青菜，  \n快乐生活在林梢。'},
 {'role': 'user', 'content': '换成两条小鱼'},
 {'role': 'assistant',
  'content': '两条小鱼，游啊游，  \n水中穿梭，乐悠悠。  \n摇摇尾巴，吐泡泡，  \n大海深处是故乡。'}]
```

### 4.3 生成工具回调提示

`illufly` 使用 `langchain` 的工具定义方法，可以参考以下示例：
```python
from illufly.tools import tool, convert_to_openai_tool
from illufly.agent import ChatQwen
from illufly.io import log
import json

@tool
def get_current_weather(location: str=None):
    """获取城市的天气情况"""
    return f"{location}今天是晴天。 "

log(ChatQwen(), "今天广州天气如何啊", tools=[convert_to_openai_tool(get_current_weather)])
```

生成结果：
```md
'{"0": {"index": 0, "id": "call_6d87845fd30b41208b9c83", "type": "function", "function": {"name": "get_current_weather", "arguments": "{\\"location\\": \\"广州\\"}"}}}'
```

### 4.4 生成工具提示的同时，执行工具

`illufly` 封装了`Tools-Calling`智能体：
```python
qwen = ChatQwen(
    tools=[convert_to_openai_tool(get_current_weather)],
    toolkits=[get_current_weather]
)

log(qwen, "今天广州可以晒被子吗？")
```

生成结果：
```md
广州今天是晴天。 

今天广州是晴天，非常适合晒被子。可以放心地把被子拿出来晾晒。

'{"0": {"index": 0, "id": "call_99a3fa145c734c9891902a", "type": "function", "function": {"name": "get_current_weather", "arguments": "{\\"location\\": \\"广州\\"}"}}}今天广州是晴天，非常适合晒被子。可以放心地把被子拿出来晾晒。'
```

### 4.5 智能体团队：执行管道

```python
from illufly.agent import ChatQwen, Pipe
from illufly.io import log

pipe = Pipe(
    ChatQwen(prompt="我是一个儿童作家，擅长写儿歌。"),
    ChatQwen(prompt="请你帮我评价文章特色，两句话即可"),
    ChatQwen(prompt="请针对我的写作成果打一个分数，给出一句话的打分点，最终给出1分至5分")
)

log(pipe, "你能帮我写一首关于兔子做梦的？四句即可。")
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

> '4分。打分点在于作品成功营造了富有童趣和想象力的氛围，语言表达既简洁又有诗意，非常适合儿童阅读，但在内容深度或情节构建上还有提升空间。'
```

### 4.6 智能体团队：扩写

```python
from illufly.agent import ChatQwen, Pipe, FromOutline, Template
from illufly.io import log, alog

writer = Pipe(
    Template("OUTLINE"),
    ChatQwen(),
    FromOutline(ChatQwen())
)

log(writer, {"task": "写一首两段儿歌，每段20个字即可，策划简单一点"})
```

生成结果：
```md
[AGENT] >>> Node 1: Template
[AGENT] >>> Node 2: ChatQwen

> # 儿歌：小星星的夜游
>
> ## 第一段：星星醒来
> <OUTLINE>
> 扩写要求：
> - 描述夜晚降临，星星出现在天空的情景
> - 引入主角小星星，它眨着眼睛好奇世界
> - 预估字数：20字
> </OUTLINE>

> ## 第二段：月亮朋友
> <OUTLINE>
> 扩写要求：
> - 介绍小星星遇到月亮，它们在夜空玩耍
> - 表达友谊与快乐的氛围
> - 预估字数：20字
> </OUTLINE>

[AGENT] >>> Node 3: FromOutline
[AGENT] 执行扩写任务 <0169-399-003>：

> 扩写要求：
> - 描述夜晚降临，星星出现在天空的情景
> - 引入主角小星星，它眨着眼睛好奇世界
> - 预估字数：20字
[AGENT] >>> Node 1: Template
[AGENT] >>> Node 2: ChatQwen
> 夜幕轻垂，万籁俱寂，星空渐渐亮起眼眸。小星星闪耀登场，好奇地眨，探秘夜的温柔。

[AGENT] 执行扩写任务 <0169-572-006>：
> 扩写要求：
> - 介绍小星星遇到月亮，它们在夜空玩耍
> - 表达友谊与快乐的氛围
> - 预估字数：20字
[AGENT] >>> Node 1: Template
[AGENT] >>> Node 2: ChatQwen
> 小星星遇见了月亮姐姐，手拉手舞动在夜空，欢笑声响彻云霄。
```