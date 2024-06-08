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

## 二、长文本创作

**创作提纲：`outline`**

```python
from textlong import outline, outline_detail
from langchain_zhipu import ChatZhipuAI

llm=ChatZhipuAI(model="glm-4")
task = """
请帮我创作500字的修仙小说，
标题为《我修了个假仙》，
主角是夏小兰，男一号是周成，
每一个章节都适用意外、打脸的线索推动
"""

md_outline = ""
for x in outline(task, llm):
    md_outline += x
    print(x, end="")

```

**结果：**

```
# 《我修了个假仙》提纲

## 第一章：误入仙途
<OUTLINE>
扩写要求：
- 字数：100字
- 创意要点：夏小兰偶然得到一本残破的修仙秘籍，开始摸索修仙之路。
- 创作思路：突出夏小兰的天真与无知，以及她误打误撞开始修仙的经过。
- 实体名称：夏小兰，秘籍。
</OUTLINE>

## 第二章：真假难辨
<OUTLINE>
扩写要求：
- 字数：100字
- 创意要点：周成发现夏小兰的秘籍是假的，却意外发现她身上有真正的修仙潜力。
- 创作思路：通过周成的视角展现夏小兰的潜力和两人之间的误会。
- 实体名称：夏小兰，周成，秘籍。
</OUTLINE>
...
```

**根据提纲扩写：`outline_detail`**

```python
md = ""
for x in outline_detail(md_outline, llm):
    md += x
    print(x, end="")
```

**结果：**

```
# 《我修了个假仙》

## 第一章：误入仙途

夏小兰，一个平凡的少女，在偶然的机会下，得到一本破旧的秘籍。这本秘籍，传说中是修仙界的至宝。然而，她还未弄清楚情况，就已经被卷入了修仙界的纷争之中。原本平淡的生活，从此变得波折四起。

## 第二章：真假难辨
...
```

**翻译：`translate`**

```python
for x in translate(md, llm, k=120, task="翻译为英文"):
    print(x, end="")
```

**结果：**

```
# I Cultivated a Fake Immortal

## Chapter 1: The Misguided Path to Immortality

Xiaolan, an ordinary girl, obtained an old secret manual by chance. This manual is rumored to be a priceless treasure in the cultivation world. However, before she could fully understand the situation, she was already caught in the midst of the disputes of the cultivation world. Her once peaceful life has since become filled with unexpected twists and turns.

## Chapter 2: Distinguishing Between Real and Fake
...
```
