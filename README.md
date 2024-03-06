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

（1）阿里云服务模型灵积（通义千问等）集成 [![langchain_dashscope](https://img.shields.io/pypi/v/langchain_dashscope.svg)](https://pypi.org/project/langchain_dashscope/)

```python
from langchain_chinese import ChatDashScope
ChatDashScope(model="qwen-max-1201")
```

（2）智谱AI [![langchain_zhipu](https://img.shields.io/pypi/v/langchain_zhipu.svg)](https://pypi.org/project/langchain_zhipu/) 

如果你要通过Langchain使用智谱AI，那么langchain_chinese会方便很多。

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
  {"input": "为什么叫三角而不是四角?"},
  config={"configurable": {"session_id": "abc123"}},
)
```

```
AIMessage(content='“三角函数”之所以称为“三角”函数，是因为它们最初是用来描述三角形内角和边长之间的关系的。在欧几里德几何中，三角形是最基本的几何形状之一，由三条边和三个内角组成。\n\n在直角三角形中，我们可以通过三角函数（正弦、余弦、正切等）来描述角度和边长之间的关系。这些函数是基于三角形内角的定义，因此被称为“三角函数”。\n\n虽然“三角函数”这个名称中包含“三角”，但实际上这些函数并不仅限于三角形的应用。它们在数学中的应用非常广泛，可以描述圆的弧度、周期性波动等各种现象，不仅仅局限于三角形。因此，“三角函数”这个名称更多是源自最初应用于三角形的背景，而非仅仅限制于三角形的概念。')
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

如果要查看短期记忆和长期记忆，可以使用如下代码：

```python
# 查看短期记忆
memory.shorterm_messages("abc123")
# 查看长期记忆
memory.longterm_messages("abc123")
```

### 3、RAG

（待补充，计划将常用RAG整合为一个单独模块）

### 4、智能体

（待补充，计划将常用智能体整合为一个单独模块）
