# 🦜🇨🇳 LangChain-Chinese
[![PyPI version](https://img.shields.io/pypi/v/langchain_chinese.svg)](https://pypi.org/project/langchain_chinese/)

**langchain_chinese** 的目标是提供中文大语言模型和中文友好的`langchain`工具。

## 一、安装

你可以使用 pip 安装：
```
pip install -U langchain_chinese langchain_zhipu
```

或者使用 poetry 安装：
```
poetry add langchain_chinese@latest langchain_zhipu@latest
```

## 二、结构化长文生成能力

`langchain_chinese` 中提供如下结构化长文档的创作模式：

- 一键直出：输入写作要求后，由AI直接创作
- （其他模式正在研发中，请参考路线图说明 roadmap.md）

**应用示范：**

```python
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from langchain_chinese import WritingTask

# 使用默认的智谱AI推理
t = WritingTask()
t.auto_write("task 给好基友写一封信, 1800字")

t.invoke("")
```