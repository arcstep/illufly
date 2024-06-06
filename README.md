# 🦜🦜🦜 textlong

[![PyPI version](https://img.shields.io/pypi/v/textlong.svg)](https://pypi.org/project/textlong/)

**textlong** 的目标是基于大语言模型提供结构化的长文本生成能力。

## 一、安装

**安装 textlong：**

你可以使用 pip 安装：

```
pip install -U textlong
```

或者使用 poetry 安装：

```
poetry add textlong@latest
```

**加载环境变量：**

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

## 二、创作长文当

**`Outline` 创作提纲：**

```python
from textlong import Writing
from langchain_zhipu import ChatZhipuAI

ol = Writing(llm=ChatZhipuAI())
ol.outline("请帮我创作500字的修仙小说，大女主设定，请给出主角的具体名字")
```

**`Detail` 依据提纲扩写：**

```python
from textlong.md import Detail

detail = Detail(ref_docs=ol, llm=ChatZhipuAI())
detail.detail()
```
