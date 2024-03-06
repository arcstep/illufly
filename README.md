# 🦜🇨🇳 LangChain-Chinese
[![PyPI version](https://img.shields.io/pypi/v/langchain_chinese.svg)](https://pypi.org/project/langchain_chinese/)

**langchain_chinese** 的目标是提供中文大语言模型和中文友好的`langchain`工具。

## 一、为什么做这个项目？
OpenAI 的大模型在引领潮流的同时，中国国内也涌现了很多优秀的大模型，
这些大模型的接口更新变化太快了，以至于 langchain 这样的框架经常无法及时更新到最新。

为了方便国内用户，我计划在 langchain_chinese 这个项目中将主要的几个中国大模型做好集成和更新维护。

## 二、安装

你可以使用 pip 安装：
```
pip install -U langchain_chinese
```

或者使用 poetry 安装：
```
poetry add langchain_chinese@latest
```

## 三、用法

### 1、模型

langchain_chinese 中为智谱和通义千问模型做了langchain集成。

（1）阿里云灵机模型（通义千问）集成 [![langchain_dashscope](https://img.shields.io/pypi/v/langchain_dashscope.svg)](https://pypi.org/project/langchain_dashscope/)

```python
from langchain_chinese import ChatDashScope
ChatDashScope(model="qwen-max-1201")
```

阿里云平台的灵积模型不仅支持通义千问公有云服务，还支持很多开源模型在平台内的部署：

  | 模型名 | 模型简介 | 模型输入输出限制 |
  | --- | --- | --- |
  | qwen-turbo | 通义千问超大规模语言模型，支持中文、英文等不同语言输入。 | 模型支持8k tokens上下文，为了保证正常的使用和输出，API限定用户输入为6k tokens。 |
  | qwen-plus | 通义千问超大规模语言模型增强版，支持中文、英文等不同语言输入。 | 模型支持32k tokens上下文，为了保证正常的使用和输出，API限定用户输入为30k tokens。 |
  | qwen-max | 通义千问千亿级别超大规模语言模型，支持中文、英文等不同语言输入。随着模型的升级，qwen-max将滚动更新升级，如果希望使用稳定版本，请使用qwen-max-1201。 | 模型支持8k tokens上下文，为了保证正常的使用和输出，API限定用户输入为6k tokens。 |
  | qwen-max-longcontext | 通义千问千亿级别超大规模语言模型，支持中文、英文等不同语言输入。 | 模型支持30k tokens上下文，为了保证正常的使用和输出，API限定用户输入为28k tokens。 |
  | qwen1.5-72b-chat | 通义千问1.5对外开源的72B规模参数量的经过人类指令对齐的chat模型。 | 支持32k tokens上下文，输入最大30k，输出最大2k tokens。 |
  | qwen1.5-14b-chat |  | 模型支持 8k tokens上下文，为了保障正常使用和正常输出，API限定用户输入为6k Tokens。 |
  | qwen1.5-7b-chat |  |  |
  | baichuan13b-chat-v1 | 由百川智能开发的一个开源的大规模预训练模型。 |  |
  | baichuan2-7b-chat-v1 | |  |
  | chatglm3-6b | ChatGLM3-6B-Base 具有在 10B 以下的预训练模型中最强的性能。 |  |

（2）智谱AI [![langchain_zhipu](https://img.shields.io/pypi/v/langchain_zhipu.svg)](https://pypi.org/project/langchain_zhipu/) 

如果你要通过Langchain使用智谱AI，那么langchain_chinese会方便很多。

支持的 model 参数：
  - glm-3-turbo
  - glm-4
  - glm-4v

**智谱官方的 Python SDK 使用了 pydanticc2，在 langserve 时会出现兼容性问题，无法生成API文档。**

invoke：
```python
from langchain_chinese import ChatZhipuAI
llm = ChatZhipuAI()
llm.invoke("讲个笑话来听吧")
```

```
AIMessage(content='好的，我来给您讲一个幽默的笑话：\n\n有一天，小明迟到了，老师问他：“你为什么迟到？”\n小明回答说：“老师，我今天看到一块牌子上写着‘学校慢行’，所以我就慢慢地走来了。”')
```

stream：
```python
for chunk in llm.stream("讲个笑话来听吧"):
    print(chunk, end="|", flush=True)
```

### 2、记忆

也许是 langchain 的发展太快了，官方团队聚焦在 langsmith 和 langgraph 的开发，记忆管理模块用法有点散乱。

按照目前 0.1.10 的文档和源码解读来看，大致可以有三种技术路线：

- 直接使用 ConversationBufferWindowMemory 等模块（缺点是：无法使用Chain和LCEL特性）
- 结合遗留的 Chain 使用 ConversationBufferWindowMemory 等模块（缺点是：未实现 stream 等方法）
- 结合RunnableWithMessageHistory 使用 ChatMessageHistory 等记忆持久化模块（缺点是无法使用 ConversationBufferWindowMemory 等方便的记忆管理模块）

我在 langchain_chinese 中提供了一种框架，将 ChatMessageHistory 系列的记忆持久化类和 ConversationBufferWindowMemory 等记忆管理类结合起来使用。

基本思路是：

- ChatMessageHistory 等模块用于记忆保存
- ConversationBufferWindowMemory 等模块用于记忆提取

代码示例如下：

STEP1 构建一个基本的链
```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai.chat_models import ChatOpenAI

model = ChatOpenAI()
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个数学老师"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)
chain = prompt | model
```

STEP2 构建一个可以管理对话轮次的记忆提取器

```python
from langchain_chinese import MemoryManager
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory

window = ConversationBufferWindowMemory(
  return_messages=True, k=2, chat_memory = ChatMessageHistory()
)

memory = MemoryManager(shorterm_memory = window)
```

**这里也可以设置 longterm_memory_factory 参数，比如设置为 redis 存储，langchain生态中有很多类似的长期记忆存储器。**

例如：
```python
memory = MemoryManager(
  shorterm_memory = window,
  longterm_memory = lambda session_id: RedisChatMessageHistory(
    session_id, url="redis://localhost:6379"
  ))
```


STEP3 使用 langchain_chinese 的 WithMemoryBinding 模块绑定链，成为新的 Runnable
```python
from langchain_chinese import WithMemoryBinding

withMemoryChain = WithMemoryBinding(
  chain,
  memory,
  input_messages_key="input",
  history_messages_key="history",
)
```

OK，接下来我们调用这个新的链。
```python
withMemoryChain.invoke(
  {"input": "三角函数什么意思？?"},
  config={"configurable": {"session_id": "abc123"}},
)
```

```
AIMessage(content='三角函数是描述角度与三角形边长之间关系的一类函数。在数学中，常见的三角函数包括正弦函数、余弦函数、正切函数等。这些函数可以帮助我们研究三角形，解决角度和边长之间的关系问题，广泛应用于几何、物理、工程等领域。')
```

```python
withMemoryChain.invoke(
  {"input": "正弦是什么?"},
  config={"configurable": {"session_id": "abc123"}},
)
```

```
AIMessage(content='正弦是三角函数中的一种，通常用sin表示。在直角三角形中，正弦函数表示某个角的对边与斜边之比。具体来说，对于角θ而言，正弦函数的定义如下：\n\nsin(θ) = 对边 / 斜边\n\n其中，对边指的是与角θ相对的边长，斜边指的是直角三角形的斜边长度。正弦函数是周期性函数，其取值范围在-1到1之间。正弦函数在数学和物理中有广泛应用，用于描述周期性现象和波动等问题。')
```

```python
withMemoryChain.invoke(
  {"input": "小学会学到吗?"},
  config={"configurable": {"session_id": "abc123"}},
)
```

```
AIMessage(content='一般来说，小学并不会涉及到正弦函数这种高级数学概念。小学阶段主要着重于基础数学知识的学习，如加减乘除、数学逻辑、几何图形等。正弦函数通常是在中学阶段的数学课程中才会开始学习和理解。在小学阶段，学生可能会了解三角形的基本概念和性质，但不会深入学习三角函数的相关知识。')
```

接下来，我们确认一下两个记忆管理变量：

```python
memory.get_shorterm_memory("abc123").buffer_as_messages
```

这是窗口记忆中显示的2轮对话：
```
[HumanMessage(content='正弦是什么?'),
 AIMessage(content='在一个直角三角形中，正弦是一个角的对边长度与斜边长度的比值。正弦函数通常用sin表示，对于一个角θ而言，其正弦值可以表示为：sin(θ) = 对边 / 斜边。正弦函数在三角学和数学中有着重要的应用，可以帮助我们计算角度和边长之间的关系。'),
 HumanMessage(content='小学会学到吗?'),
 AIMessage(content='正弦函数通常不是小学阶段的数学内容，因为它涉及到三角函数和三角学的概念，通常在初中或高中阶段学习。小学阶段的数学教育主要集中在基本的数学运算、几何图形、分数、小数等方面，正弦函数等高级数学概念一般在更高年级的学习中才会接触到。')]
```

```python
memory.get_shorterm_memory("abc123").chat_memory.messages
```

这是内存中的完整记忆（现在保存在内存中，你也可以保存在redis等数据库中）：
```
[HumanMessage(content='三角函数什么意思？?'),
 AIMessage(content='三角函数是指在直角三角形中，角的大小关系到三角形的边长比例的函数。常见的三角函数包括正弦函数、余弦函数、正切函数、余切函数、正割函数和余割函数等。这些函数在数学和物理中有着广泛的应用，可以描述角度和三角形之间的关系。'),
 HumanMessage(content='正弦是什么?'),
 AIMessage(content='在一个直角三角形中，正弦是一个角的对边长度与斜边长度的比值。正弦函数通常用sin表示，对于一个角θ而言，其正弦值可以表示为：sin(θ) = 对边 / 斜边。正弦函数在三角学和数学中有着重要的应用，可以帮助我们计算角度和边长之间的关系。'),
 HumanMessage(content='小学会学到吗?'),
 AIMessage(content='正弦函数通常不是小学阶段的数学内容，因为它涉及到三角函数和三角学的概念，通常在初中或高中阶段学习。小学阶段的数学教育主要集中在基本的数学运算、几何图形、分数、小数等方面，正弦函数等高级数学概念一般在更高年级的学习中才会接触到。')]
```

### 3、RAG

（待补充，计划将常用RAG整合为一个单独模块）

### 4、智能体

（待补充，计划将常用智能体整合为一个单独模块）
