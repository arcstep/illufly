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

`textlong` 中提供如下创作工具：

- `WritingTask`：用于生成结构化长文

**1. 加载环境变量：**

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

**2. 创建`WritingTask`实例：**

```python
from textlong import WritingTask
from langchain_openai import ChatOpenAI

task = WritingTask(llm=ChatOpenAI())
```

**3. 使用`auto_write`方法自动生成一段长文：**

```python
task.auto_write("task 给好基友写一封信, 1800字，分4段就行")
```

**4. 使用`repl_write`方法控制台，在人工干预过程中生成一段长文：**

```python
task.repl_write("task 给好基友写一封信, 1800字，分4段就行")

## ...
## 接下来，你可以一直输入 ok 指令确认生成的内容，获得与 auto_write 类似的效果
```

**5. 你可以查看生成的提纲（也可以在repl模式中输入 outlines）：**

```python
# 查看创作大纲
task.invoke("outlines")['reply']
```

**6. 或者查看文字成果：**

```python
task.invoke("texts")['reply']
```

**7. 使用`invoke`方法执行`help`指令，以获得帮助:**

```python
task.invoke("help 我在repl模式中还可以做什么？")
```

