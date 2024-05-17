# 🦜🦜🦜 textlong
[![PyPI version](https://img.shields.io/pypi/v/textlong.svg)](https://pypi.org/project/textlong/)

**textlong** 的目标是基于大语言模型提供结构化的长文本生成能力。

## 一、安装

你可以使用 pip 安装：
```
pip install -U textlong
```

或者使用 poetry 安装：
```
poetry add textlong@latest
```

## 二、结构化长文生成能力

`textlong` 中提供如下结构化长文档的创作模式：

- 一键直出：输入写作要求后，由AI直接创作
- （其他模式正在研发中，请参考路线图说明 [路线图](https://github.com/arcstep/textlong/blob/main/roadmap.md)）

**应用示范：**

```python
import os
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from textlong import WritingTask

# 使用默认的智谱AI推理
t = WritingTask()
t.auto_write("task 给好基友写一封信, 1800字")

t.invoke("")
```