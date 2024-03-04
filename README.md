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

目前专门提供了 [智谱AI的langchain集成](https://github.com/arcstep/langchain_zhipuai) ，很快会更新通义千问、文心一言等其他的大模型。

- 智谱通用大模型
  - glm-3-turbo
  - glm-4
  - glm-4v

<div class="alert alert-warning">
<b>使用langchain_chinese时，最好不要单独安装 zhipuai 包</b><br>
由于 langserve 要求使用 pydantic_v1，否则存在很多兼容性问题，
因此特意在 langchain_zhipu 项目中克隆了该项目，并做出少许修改，以便将 pydantic 从 v2 降级到 v1 。<br>
如果不经过这个处理，你就必须安装 v2 版本的pydantic来兼容 zhipuai，于是在 langserve 时你会发现无法生成API文档。
</div>

在安装 langchain_chinese 时已经自动安装了 langchain_zhip。

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
