**langchain_chinese** 的目标是提供中文大语言模型和中文友好的`langchain`工具。

## 为什么做这个项目？
OpenAI 的大模型在引领潮流的同时，中国国内也涌现了很多优秀的大模型，
这些大模型的接口更新变化太快了，以至于 langchain 这样的框架经常无法及时更新到最新。

为了方便中国国内用户使用，我计划在 langchain_chinese 这个项目中将几个主要的中国大模型做好集成和更新维护。

### 模型

目前支持的只有智谱AI，很快会更新通义千问、文心一言等其他的大模型。

- 智谱通用大模型
  - glm-3-turbo
  - glm-4

### 路线图

智谱AI的V4版本通用大模型所有参数都支持了，但还需要做其他的工作：

- 支持异步方法
- 支持智谱的Tool回调
- 支持事件流的callback
- 支持内置的search工具
- 支持内置的检索工具
- 支持图片生成能力
- 支持调用中的异常
- 提供便利的bind_tools方法
- 提供基于Tool调用的Agent
- ...

有计划，但尚未支持的模型：

- 阿里云积灵各类模型
- 阿里云百炼各类模型
- 千帆各类模型
- 文心一言
- 讯飞星火


## 安装

你可以使用 pip 安装：
```
pip install -U langchain_chinese
```

或者使用 poetry 安装：
```
poetry add langchain_chinese
```

## 使用

### invoke
```python
from langchain_chinese import ZhipuAIChat
llm = ZhipuAIChat()
llm.invoke("讲个笑话来听吧")
```

```
AIMessage(content='好的，我来给您讲一个幽默的笑话：\n\n有一天，小明迟到了，老师问他：“你为什么迟到？”\n小明回答说：“老师，我今天看到一块牌子上写着‘学校慢行’，所以我就慢慢地走来了。”')
```

### stream
```python
llm.invoke("讲个笑话来听吧")
```
