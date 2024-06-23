# 🦜🦜🦜 textlong

[![PyPI version](https://img.shields.io/pypi/v/textlong.svg)](https://pypi.org/project/textlong/)

**textlong** 的目标是基于大语言模型提供结构化的长文本生成能力。

# 《textlong 使用指南》

## 1 环境准备

### 1.1 使用 dotenv 管理环境变量

将 APIKEY 和项目配置保存到`.env`文件，再加载到进程的环境变量中，这是很好的实践策略。

这需要使用 dotenv 包，它可以帮助我们管理项目中的环境变量。

创建和配置`.env`文件，你需要在你项目的根目录下创建一个名为`.env`的文件（注意，文件名以点开始）。在这个文件中，你可以定义你的环境变量，例如：

```
ZHIPUAI_API_KEY="你的智谱AI API密钥"
TEXTLONG_FOLDER="你的项目目录"
```

为此，你可能需要先安装 python-dotenv 包：

```bash
pip install python-dotenv
```

然后在 Python 代码中，使用以下代码片段来加载`.env`文件中的环境变量：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

### 1.2 申请大语言模型

当你决定申请大语言模型服务时，可以选择美国公司如 OpenAI 或 Claude 提供的服务，也可以选择中国的智谱 AI 等国内服务。这些服务通常都会提供详细的申请流程指引。申请过程中，你需要填写相关信息，并按照指引完成相应的步骤。成功申请后，你会获得一个 API_KEY，这是你调用这些大语言模型服务的唯一凭证。

获得 API_KEY 后，为了确保其安全性和便捷性，你应该将其配置到项目根目录下的`.env`文件中，例如：

**你的.env 文件**

```
ZHIPUAI_API_KEY="YOUR_API_KEY_NAME"
```

这种方式不仅能保护你的敏感信息，还能让你的代码更加整洁、易于管理。

## 2 textlong 的安装与加载

### 2.1 安装 textlong 包

在 Python 中安装 textlong 包非常简单，以下命令会尝试安装最新版本的 textlong：

```sh
pip install textlong
```

为了确保安装的是最新版本，可以在命令中添加`--upgrade`选项，如下：

```sh
pip install --upgrade textlong
```

## 3 使用 textlong 创作长文

### 3.1 在 jupyter 环境中使用 textlong

**安装 JupyterLab**

在使用 textlong 之前，首先需要确保你的环境中安装了 JupyterLab。JupyterLab 是一个交互式的开发环境，非常适合进行数据分析和机器学习项目。你可以通过以下命令安装 JupyterLab：

```sh
pip install jupyterlab
```

安装完成后，可以通过运行以下命令来启动 JupyterLab：

```sh
jupyter-lab
```

**建立笔记**

在新的笔记中，首先需要导入 textlong 包。在进行导入之前，请确保已经按照前面的步骤正确安装了 textlong 包：

首先，加载你的环境变量，这样你就可以安全地访问 API 密钥：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

接下来，导入 textlong 包和所需的模型：

```python
from textlong import Project
from langchain_zhipu import ChatZhipuAI
```

现在，你可以初始化一个 Project 对象，如下所示：

```python
p = Project(ChatZhipuAI(model="glm-4"), project_id="demo")
p
```

这里`project_id`是你为 textlong 项目指定的唯一标识符。确保你使用的是正确的 API 模型名称和项目 ID。

恭喜你，现在可以使用 textlong 包来创作长文了！

### 3.2 创作提纲

从一个简单的例子开始，假设我们要创作的是一部 10000 字的修仙小说，标题为《我修了个假仙》，主角是夏小兰，男一号是周成，每个章节都将以意外和打脸的线索推动情节。

接下来，使用 textlong 的`outline`方法来创建提纲。

```python
task = "请帮我创作10000字的修仙小说，标题为《我修了个假仙》，主角是夏小兰，男一号是周成，每一个章节都适用意外、打脸的线索推动。"
p.outline("提纲.md", task)
```

当你运行上述代码后，textlong 会根据你的任务描述自动生成一份提纲。提纲将包括小说的章节划分和每个章节的关键情节。你可以根据这个提纲来进行文章的扩写。

生成的结果如下：

```md
# 《我修了个假仙》

## 第一章：星辰之女的觉醒

<OUTLINE>
夏小兰一直被认为拥有神秘力量，却在一次意外中被揭露出她的能力并不如外界传言那般强大，实际上她修了个“假仙”。这次觉醒让她在村中受尽白眼，决心踏上寻找真正修仙之道的旅程。

扩写要求：

- 预估字数：1000
- 创意要点：意外揭露，能力不足，决心追求真相
- 创作思路：通过主角的失落和觉醒，引出后续成长和冒险
- 涉及实体名称：夏小兰，星辰之女

</OUTLINE>

...
```

### 3.3 文章扩写

接下来，是根据提纲扩写：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input="提纲.md"
)
```

运行上述代码，textlong 将根据“提纲.md”中的结构，生成一篇名为“我修了个假仙人.md”的文章初稿。

也许你希望对生成的文章进行微调，以更好地符合你的创作风格或文章需求。
为此，你可以像下面这样调整`from_outline`方法的参数：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input="提纲.md",
    task="多使用人物细节、对话描写、打斗描写，减少抽象叙事"
)
```

在这个调整后的代码中，我们添加了一个额外的参数`task`，用于指导 AI 在生成文章时要特别关注的方面。这样，生成的文章将包含更多的人物细节、对话和打斗描写，同时减少抽象的叙述。

生成结果如下：

```md
# 《我修了个假仙》

## 第一章：星辰之女的觉醒

夏小兰，一直被村民视为拥有神秘力量的星辰之女。然而，在那次意外中，她的真实能力被揭穿，原来她修了个“假仙”。村中的嘲笑与白眼，让她痛不欲生。夏小兰站在村口，紧握双拳，眼中闪过坚定：“我一定要找到真正的修仙之道，证明给所有人看！”

那天，阳光透过云层洒在她的脸上，仿佛预示着她即将踏上的艰难旅程。夏小兰迈开坚定的步伐，离开这个让她充满失落的地方，去寻找属于自己的真相。

...
```

### 3.4 引用素材管理

可能你希望在创作过程中，在每个步骤都共享一些知识，例如在创作长篇小说时的人物设定。

你可以先使用用`idea`方法生成关于小说人物的设定：

```python
task = "我要写一个修仙小说，主角是夏小兰，男一号是周成，请帮我设想一下这两个人的出身，要非常魔幻。"
p.idea("人物设定.md", task)
```

接下来，通过`from_outline`方法中的`knowledge`参数来引用它们。如下示例：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input="提纲.md",
    task="多使用人物细节、对话描写、打斗描写，减少抽象叙事",
    knowledge=["人物设定.md"]
)
```

注意，`idea`、`outline`等方法中同样可以使用`knowledge`参数。

## 4 一键直出

你在上述项目中使用过的方法都已经被日志记录，因此可以通过`save_script`将你手工执行过的动作保存到 `project_script.yml`脚本文件，再执行`run_script`实现一键直出。

**保存自动化脚本**
首先使用`save_script`保存可执行的脚本清单，这会生成或更新项目文件夹中的 `project_script.yml`文件：

```python
# 加载
p.save_script()
```

**查看`project_script.yml`**

`project_script.yml`的结构是一个`yaml`文件，你也手工收工编辑或对生成或的脚本裁剪。

**执行下面的脚本就可以重新生成结果：**

```python
# 执行
p.run_script()
```
