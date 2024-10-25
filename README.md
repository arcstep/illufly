# ✨🦋 illufly

[![PyPI version](https://img.shields.io/pypi/v/illufly.svg)](https://pypi.org/project/illufly/)

`illufly` 是 `illution butterfly` 的缩写，中文为"幻蝶"。

**illufly** 是一个简单易用并具有自我进化能力的智能体应用框架。

我们在使用 AI 时都会报以幻想，希望它能随着时间推移从小白变成老手。<br>
但我们也希望这个进化过程不用操太多心，而是像小孩子慢慢长大一样，自然而然地完成。

这正是 `illufly` 的设计理念。

目前 `illufly` 随着版本迭代，已经支持了 RAG应用、多种智能体推理模式，并具有了一定的进化能力。

* [《illufly 快速指南》](https://github.com/arcstep/illufly/wiki/Home)

**入门指南**
* [安装配置指南](https://github.com/arcstep/illufly/wiki/安装指南)
* [模块导入参考](https://github.com/arcstep/illufly/wiki/模块参考)
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


## 使用示例

**1. 基本使用**

在了解 illufly 的进化能力之前，你应当先了解它的基本使用。

illufly 最主要是封装了 ChatAgent 基类，在进一步实现千问、智谱以及 OpenAI 等大模型厂家的接口后，获得了 ChatQwen、ChatZhipu 以及 ChatOpenAI 等子类。

由于 ChatAgent 封装了多轮对话、工具回调、流输出等常用能力，ChatQwen 等子类可以直接使用这些能力。

```python
from illufly.chat import ChatQwen

chat = ChatQwen()
chat("你是什么模型？")
```

```
输出内容: (我是一个流式输出的动画)
```

**2. 让你的 AI 越聊越懂**

基本的进化策略是：你跟 AI 聊的内容可以被它记住，并根据这些记忆进化出越来越懂你的能力。<br>
但实际上你也不想把 AI 变成一只记住任何人说话的鹦鹉。你的 AI 应当能够分辨该记住谁的话、记住什么话。



**2. 工具回调**

ChatAgent 在使用工具回调时非常简洁，只需要将工具列表传递给类的实例即可，不需要多余的代码。

```python
from illufly.chat import ChatQwen

def poet(input: str):
    """我是诗人，擅长作诗。"""
    return "请看我的新作：\n大海啊, 全是水"

chat = ChatQwen(tools=[poet])
chat("帮我写一首小诗？")
```

    上述代码会触发 openai 的工具回调，并将 poet 做的诗作为结果返回给你。

**3. 复杂推理**

你已经学会直接使用 OpenAI 风格的工具回调。<br>
但你可能还想使用其他推理模式，illufly 中已经实现这些推理风格:

| FlowAgent子类 | 推理方式 | 论文 |
|:----|:--------|:------------|
|ReAct|一边推理一边执行|[ReAct](https://arxiv.org/abs/2210.03629) |
|ReWOO|一次性规划所有步骤后一起执行|[ReWOO](https://arxiv.org/abs/2305.18323) |
|PlanAndSolve|一边修订总体计划一边执行|[Plan-and-Solve](https://arxiv.org/abs/2305.04091) |

你也可以参考 illufly 的源码，实现自己的推理模式。

下面是一个 ReAct 使用的示例，与直接使用 ChatAgent 非常相似：

```python
from illufly.chat import ChatQwen, ReAct

def tool1(input: str):
    """我是一个会写诗的工具"""
    return "大海啊, 全是水"

chat = ReAct(
    planner=ChatQwen(tools=[tool1])
)
chat("你是什么模型？")
```

**4. 多智能体协作**

illufly 也允许你定义多个智能体，并让它们协作完成任务。

下面的 FlowAgent 代码实现了 **Reflection** 推理模式。
代码中定义了一个条件循环，写手和评分专家协作完成一首儿歌的创作和评分。

```python
from illufly.chat import FlowAgent, ChatQwen, Selector

writer = ChatQwen(
    name="写手",
    memory=("system", "你是一个写手")
)

evaluator = ChatQwen(
    name="评分专家",
    memory=("system", "你是一个评分专家，根据对方写的内容评价1分-5分，仅输出评价和最终结果")
)

def should_continue():
    return "__END__" if "5" in evaluator.last_output else "写手"

flow = FlowAgent(writer, evaluator, Selector(condition=should_continue))

flow("你能帮我写一首关于兔子的四句儿歌?")
```

## 知识塔

如果你想学习 illufly 的全部内容，下面是一个知识结构的指引。

该图不是模块的继承关系，而是知识主题的依赖关系。
也就是说，如果你要了解某个上层模块，就必须先了解下层模块。

```mermaid
graph TD
    Config[[Config<br>环境变量/默认配置]]
    Runnable[Runnable<br>绑定机制/流输出/handler]

    Flow[FlowAgent<br>顺序/分支/循环/自定义]

    Agent(ChatAgent<br>记忆/工具/进化)
    Selector(Selector<br>意图/条件)
    BaseAgent(BaseAgent<br>工具/多模态)
    Messages[Messages<br>文本/多模态/模板]
    PromptTemplate[[PromptTemplate<br>模板语法/hub]]

    MarkMeta[[MarkMeta<br>切分标记/元数据序列化]]
    Retriever[Retriever<br>理解/查询/整理]

    Flow --> Agent
    Agent --> Selector --> Runnable --> Config
    Agent --> BaseAgent --> Runnable
    Agent --> Messages -->  PromptTemplate --> Runnable
    Agent --> Retriever --> MarkMeta --> Runnable

    style Agent stroke-width:2px,stroke-dasharray:5 5
    style BaseAgent stroke-width:2px,stroke-dasharray:5 5

```

## 安装指南

**安装 `illufly` 包**

```sh
pip install illufly
```

**推荐使用 `dotenv` 管理环境变量**

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



