# 🦋✨ illufly

[![PyPI version](https://img.shields.io/pypi/v/illufly.svg)](https://pypi.org/project/illufly/)

`illufly` 是 `illution butterfly` 的缩写，中文为“幻蝶”。

**illufly** 的目标是快速构建多智能体的对话和写作场景。

# 《幻蝶智能体 - illufly 使用指南》

## 1. 模型支持

目前，框架主要支持以下大模型接口：
- OpenAI 或协议兼容的模型
- 阿里云的通义千问通用模型等
- 智谱AI的GLM4系列通用模型
- （... 即将开放其他大模型接口支持）
- （... 即将开放其他多模态模型接口支持）

## 2 使用 dotenv 管理环境变量

将 APIKEY 和项目配置保存到`.env`文件，再加载到进程的环境变量中，这是很好的实践策略。

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

`illufly`中的所有智能体都使用流输出，并支持异步和SSE调用。
因为流输出就是迭代器，想要打印结果就要写类似下面的代码：

```python
for x in qwen.call("请你帮我写封情书"):
    print(x, end="")
```

这类代码太常见，因此 `illufly` 中提供了`log`语法糖函数来替代。

### 4.1 创建对话应用

使用下面极简的代码，就可以构建基于通义千问大模型的对话应用。
下面的代码中使用了`log`函数，在执行代码的环境中才可以看到：输出实际上是一个字或一个词蹦出来的流式输出。
```python
from illufly.agent import ChatQwen
from illufly.io import log

 # 要使用这个通义千问，需要先安装 `dashtop` 包
 # 并配置好相应的 DASHSCOPE_API_KEY
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

`ChatQwen`是一个智能体对象，已经自带了记忆、工具回调等能力。
```python
from illufly.agent import ChatQwen
from illufly.io import log

# 简单的系统提示语可以在智能体定义时声明，帮助确定角色、任务等
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

连续提问，它依然懂你：
```python
log(qwen, "换成两条小鱼")
```

生成结果：
```md
两条小鱼，游啊游，  
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
  'content': '两条小鱼，游啊游，  \n水中穿梭，乐悠悠。  \n摇摇尾巴，吐泡泡，  \n大海深处是故乡。'}]
```

### 4.3 生成工具回调提示

无需额外代码，`illufly`中的智能体对象已经支持工具的使用，只需要提供`tools`参数和`toolkits`参数即可。

`illufly` 保留了少部份 `langchain` 能力，定义工具的方法和类是其中之一，这部份可以参考`langchain`官网：[https://python.langchain.com/v0.2/docs/how_to/custom_tools/]。

以下示例是定义工具和使用工具的过程：
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

请注意：这里并没有真正执行工具，只是生成了工具提示。
想要执行，还需要你提供`toolkits`参数。

### 4.4 生成工具提示的同时，执行工具

还是那个`illufly` 智能体对象，但提供`toolkits`参数之后，就变成了`Tools-Calling`风格的智能体。这在`langchain`中也被称为`OpenAI风格的智能体`。

```python
qwen = ChatQwen(
    tools=[convert_to_openai_tool(get_current_weather)],
    toolkits=[get_current_weather]
)

log(qwen, "今天广州可以晒被子吗？")
```

生成结果（第一句是工具回调输出的结果，第二句是工具回调后大模型再次生成的流长文本）：
```md
广州今天是晴天。 

今天广州是晴天，非常适合晒被子。可以放心地把被子拿出来晾晒。
```

你也可以通过设置`verbose=True`来查看工具调用详情：

```python
log(qwen, "今天广州可以晒被子吗？", verbose=True)
```

生成结果（增加的中括号开头部份，是大模型第一次推理得出的工具和参数要求）：
```md
[TOOLS_CALL_CHUNK] {"index": 0, "id": "call_8f5d146a77b24d9c97b7ec", "type": "function", "function": {"name": "get_current_weather", "arguments": ""}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {"arguments": "{\"location\": \""}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {"arguments": "广州\"}"}}
[TOOLS_CALL_CHUNK] {"index": 0, "id": "", "type": "function", "function": {}}
[TOOLS_CALL_FINAL] {"0": {"index": 0, "id": "call_8f5d146a77b24d9c97b7ec", "type": "function", "function": {"name": "get_current_weather", "arguments": "{\"location\": \"广州\"}"}}}
广州今天是晴天。 

今天广州是晴天，非常适合晒被子。
```

### 4.5 智能体团队：执行管道

将前面用过的智能体连接起来，就可以形成多智能体团队。
`Pipe`对象会把多个智能体对象组织起来，分工协作，共同完成任务，使用方法也与普通智能体类似。

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
```

加入到 `Pipe` 中的智能体对象，都可以使用自己的大模型、提示语、工具箱。其协作过程就像流水线，前一个智能体的输出，直接作为下一个智能体的输入。这是多智能体协作方式的一种，称为`流水线协作`。

`illufly` 中还支持其他协作方式，如`提纲扩写`、`讨论`、`汇总`等。

### 4.6 智能体团队：提纲扩写

下面是一个根据提纲扩写的例子，主要包括生成提纲和扩写两个部份。但提纲部份使用了较复杂的提示语模板，因此单独使用了`Template`对象作为流水线协作的开始，这样可以接受多参数的输入。

`illufly` 中类似的提示语模板还有很多，并支持对提示语模板的查看、克隆、自定义等管理功能。这些模板机制可以让作者按照自己的意愿精细控制写作过程。

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

由于上面的定义非常典型，因此未来会设计一个语法糖对象，在不隐藏细节的情况下将这部份代码进一步简化。

生成结果是连续的（如果不通过指令控输出字数，可以轻松输出万字长文）：
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

### 4.7 智能体团队：多模态输出

事实上，通过`illufly`可以进一步控制扩写的每个段落，以及对每个段落进行重写，而通过多智能体机制，也可以融合多模态输出到写作过程。

例如：

```python
# 例子很快到来
# 请耐心等待 ...
```