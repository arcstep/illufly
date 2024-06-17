# 🦜🦜🦜 textlong

[![PyPI version](https://img.shields.io/pypi/v/textlong.svg)](https://pypi.org/project/textlong/)

**textlong** 的目标是基于大语言模型提供结构化的长文本生成能力。

**注意：以下文字全部使用`textlong`自动生成：**

# 使用 textlong 指南

## 环境准备

### 使用 dotenv 管理环境变量

**使用 dotenv 管理环境变量**

dotenv 是一种在开发过程中管理环境变量的便捷方式，通过创建一个`.env`文件来集中存储项目配置信息，如 API 密钥和数据库凭据等，从而避免将这些敏感信息直接硬编码在代码中。

要使用 dotenv，首先需要安装`python-dotenv`包，这是一个可以在 Python 应用程序中读取`.env`文件的库。

```bash
pip install python-dotenv
```

创建和配置`.env`文件，应将其放置在项目的根目录下。以下是一个`.env`文件示例，它包含了 textlong 指南中可能需要用到的环境变量：

```
ZHIPUAI_API_KEY="xxxxxxx" # 这是你的智谱AI等大语言模型的API密钥
TEXTLONG_FOLDER="你的项目目录" # 指定textlong使用的文件夹路径
```

在 Python 脚本中，使用以下代码加载`.env`文件中的变量：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

这行代码将搜索项目中的`.env`文件并加载其内容，`override=True`参数确保环境变量即使已经存在于环境中也会被覆盖。

**申请大语言模型**

在开始使用 textlong 之前，你需要申请一个大语言模型的 API_KEY。你可以选择美国公司 OpenAI、Claude 等提供的大语言模型，或是中国的智谱 AI 等。以智谱 AI 为例，你需要前往其官方网站，按照指引注册账户并申请 API_KEY。

获取 API_KEY 后，将其添加到`.env`文件中，如下所示：

```
ZHIPUAI_API_KEY="你的智谱AI API密钥"
```

通过以上步骤，你就可以在项目中安全地使用和管理环境变量，同时确保你的 API 密钥不会泄露到版本控制系统中。

### 申请大语言模型

你可以选择申请美国公司 OpenAI、Claude 等提供的大语言模型，或者选择我国的企业，如智谱 AI 等提供的大语言模型服务。在申请过程中，你需要按照官方网站的指引进行注册，并根据提示完成 API_KEY 的申请。申请成功后，你将获得一个独一无二的 API 密钥，这个密钥将用于在 textlong 中调用大语言模型服务。

获得 API_KEY 后，你需要将其配置到项目的`.env`文件中，以便在 Python 脚本中安全地管理和使用这些环境变量。以下是配置`.env`文件的步骤：

1. 打开项目根目录下的`.env`文件（如果不存在，请自行创建）。
2. 在`.env`文件中添加以下内容：

```
ZHIPUAI_API_KEY="你的智谱AI API密钥"
```

请注意，将`"你的智谱AI API密钥"`替换为你实际申请到的 API 密钥。

3. 保存并关闭`.env`文件。

通过以上步骤，你已完成大语言模型 API_KEY 的申请和配置，现在可以在 textlong 项目中使用这个 API_KEY 来调用大语言模型服务了。

## textlong 的安装与加载

### 安装 textlong 包

为了安装 textlong 包，你需要在命令行或终端中使用 pip 命令。以下是一个示例命令，用于安装 textlong 的最新版本：

```sh
pip install textlong==最新版本号
```

在执行此命令前，请确保你的 Python 环境已经安装并配置好了 pip。通常情况下，当你安装 Python 时，pip 会自动安装。若要查找最新版本号，可以访问 Python 包索引网站（PyPI），搜索 textlong，并在项目页面上找到最新版本。

如果你不清楚最新版本号，也可以使用以下命令来安装最新版本的 textlong 包：

```sh
pip install --upgrade textlong
```

这将自动查找当前可用的最新版本并将其安装到你的 Python 环境中。

请记得在安装前激活你的虚拟环境（如果你使用虚拟环境的话），这样可以确保 textlong 包被安装在当前虚拟环境中，而不是全局 Python 环境中。

## 使用 Project 创作长文

### 建议在 jupyter 环境中使用

### 在 Jupyter 中导入 textlong

#### 安装 Jupyter

Jupyter Notebook 是一个开源的 Web 应用程序，允许你创建和共享代码、方程、可视化和叙述文本。为了使用 textlong 在 Jupyter 环境中创作长文，你需要先安装 Jupyter。你可以通过以下命令使用 pip 来安装 Jupyter：

```sh
pip install notebook
```

确保你的虚拟环境已经激活，以便将 Jupyter 安装到当前环境中。

#### 建立笔记

安装 Jupyter 之后，你可以通过以下命令启动 Jupyter Notebook：

```sh
jupyter notebook
```

这将在你的默认浏览器中启动 Jupyter Notebook。之后，你可以创建一个新的笔记（Notebook）来开始工作。

#### 导入 textlong 包

在新的 Jupyter 笔记中，首先需要导入 textlong 包和其他必要的库。以下是如何操作的示例代码：

```python
# 导入dotenv库以加载环境变量
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

# 导入textlong包中的Project类
from textlong import Project

# 导入你的大语言模型API
from langchain_zhipu import ChatZhipuAI

# 实例化Project类，并传入你的大语言模型实例和项目ID
p = Project(ChatZhipuAI(model="glm-4"), project_id="project")
p
```

在上面的代码中，首先我们加载了环境变量，这是为了确保我们能够访问到之前在 `.env` 文件中配置的智谱 AI API 密钥。然后，我们导入了 `Project` 类，并创建了 `Project` 的一个实例，将 ChatZhipuAI 实例和项目 ID 传递给了它。

通过以上步骤，你现在可以在 Jupyter Notebook 环境中使用 textlong 进行长文的创作了。

### 创作提纲

在 textlong 中创作提纲是一个组织和规划长文的有效方法。通过使用 textlong 的`from_idea`方法，你可以快速将你的想法转换成一个结构化的提纲，为后续的文章创作奠定基础。以下是如何使用 textlong 创作提纲的详细步骤和示范。

首先，你需要明确你的创作任务。在这个例子中，任务是为夏小兰和周成这两位角色创作一部 500 字的修仙小说，标题为《我修了个假仙》。小说的每一个章节都应该包含意外和打脸的元素，以增加故事的趣味性和紧张感。

以下是使用 textlong 创作提纲的代码示范：

```python
task = "请帮我创作500字的修仙小说，标题为《我修了个假仙》，主角是夏小兰，男一号是周成，每一个章节都适用意外、打脸的线索推动。"
p.from_idea("提纲.md", task, prompt_id="OUTLINE")
```

在上面的代码中，`from_idea`方法接收三个参数：提纲文件的名称（在这个例子中是"提纲.md"），创作任务的描述，以及一个可选的`prompt_id`，它有助于区分不同的提纲。

当你运行这段代码时，textlong 会根据你的任务描述创建一个结构化的提纲，并保存在指定的文件中。这个提纲将包含一系列的章节标题和概要，每个章节都围绕意外和打脸的线索来构建故事情节。

提纲创建后，你可以根据需要进一步细化每个章节的内容。这个过程可以通过迭代和修改提纲文件来完成，直到你对故事的框架感到满意为止。

接下来，你可以使用 textlong 的其他功能，如`add_chapter`和`extend_chapter`，来实际扩写每个章节的内容，逐步构建起整个小说。

### 文章扩写

在 textlong 中，基于提纲进行文章扩写是一个高效且具有指导性的过程。你可以通过`from_outline`方法，根据已有的提纲文件创建文章的初稿。以下是如何使用 textlong 进行文章扩写的详细步骤。

首先，你需要确定输出的文件名和输入的提纲文件。使用`from_outline`方法，你可以将提纲转换成文章的草稿。例如，我们的目标是创建一篇名为“我修了个假仙人.md”的小说，基于之前创建的“提纲.md”文件。

基本代码示范已经给出，它将直接根据提纲生成文章。然而，你可能希望对生成效果进行微调，使其更符合你的创作意图。此时，可以通过添加额外的参数来指导 textlong 的生成过程。在上述示例中，我们要求 textlong 在生成内容时，“多使用人物细节、对话描写、打斗描写，减少抽象叙事”。

为了更具体地指导文章扩写，你可以按照以下步骤操作：

1. 分析提纲，确定每个章节的关键情节和需要扩写的内容。
2. 使用`from_outline`方法，根据提纲的结构和你的创作要求，生成每个章节的初稿。
3. 针对生成的初稿，进行细致的阅读和修改，确保人物形象鲜明、情节连贯、对话自然。
4. 若有需要，可以多次迭代，利用 textlong 的其他功能（如`extend_chapter`）进一步完善内容。

至于生成素材的部分，textlong 同样提供了强大的支持。你可以通过`from_idea`方法，提出具体的要求，让 textlong 帮助你设想人物的出身等细节。

例如，为了丰富夏小兰和周成这两位主角的背景设定，你提出了一个魔幻风格的出身设定要求。通过以下代码，你可以生成相关的人物设定：

```python
task = "我要写一个修仙小说，主角是夏小兰，男一号是周成，请帮我设想一下这两个人的出身，要非常魔幻。"
p.from_idea("人物设定.md", task)
```

# 使用 textlong 指南

## 环境准备

### 使用 dotenv 管理环境变量

dotenv 是一个在开发中常用的工具，它可以帮助我们管理项目中的环境变量。通过使用 dotenv，我们可以将敏感信息（如 API 密钥）与代码分离，从而避免在代码库中直接暴露这些信息。Python 中的 dotenv 包可以通过读取`.env`文件来加载环境变量。

安装 python-dotenv 包非常简单，你可以通过 pip 命令来完成安装：

```bash
pip install python-dotenv
```

创建和配置`.env`文件，你需要在你项目的根目录下创建一个名为`.env`的文件（注意，文件名以点开始）。在这个文件中，你可以定义你的环境变量，例如：

```
ZHIPUAI_API_KEY="你的智谱AI API密钥"
TEXTLONG_FOLDER="你的项目目录"
```

在 Python 代码中，你可以使用以下代码片段来加载`.env`文件中的环境变量：

```python
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)
```

接下来，你可以通过`os.environ`来访问这些环境变量：

```python
import os
api_key = os.environ.get('ZHIPUAI_API_KEY')
```

对于大语言模型的申请，你可以选择申请美国公司 OpenAI、Claude 等提供的大语言模型，或者选择中国的智谱 AI 等大语言模型服务。申请完成后，你会获得一个 API_KEY，这是你调用相应服务的凭证。

获得 API_KEY 后，你需要将其配置到之前创建的`.env`文件中，这样在代码中就可以安全地引用这个密钥了。

### 申请大语言模型

当你决定申请大语言模型服务时，可以选择美国公司如 OpenAI 或 Claude 提供的服务，也可以选择中国的智谱 AI 等国内服务。这些服务通常都会提供详细的申请流程指引。申请过程中，你需要填写相关信息，并按照指引完成相应的步骤。成功申请后，你会获得一个 API_KEY，这是你调用这些大语言模型服务的唯一凭证。

获得 API_KEY 后，为了确保其安全性和便捷性，你应该将其配置到项目根目录下的`.env`文件中。这样，你的代码在需要引用这个密钥时，可以通过以下方式轻松获取：

```python
import os
api_key = os.environ.get('YOUR_API_KEY_NAME')
```

这里的`YOUR_API_KEY_NAME`应该与你在`.env`文件中定义的环境变量名称一致。这种方式不仅能保护你的敏感信息，还能让你的代码更加整洁、易于管理。

## textlong 的安装与加载

### 安装 textlong 包

在 Python 中安装 textlong 包非常简单，只需要使用 pip 命令即可。以下是一个安装 textlong 包的示例命令，它会尝试安装最新版本的 textlong：

```sh
pip install textlong
```

为了确保安装的是最新版本，可以在命令中添加`--upgrade`选项，如下：

```sh
pip install --upgrade textlong
```

执行上述命令时，请确保你的 pip 工具是最新版本，以避免安装过程中可能出现的兼容性问题。

如果你正在使用虚拟环境，确保你已经激活该环境，然后再运行上述 pip 命令，这样 textlong 包将被安装到虚拟环境中，而不会影响全局 Python 环境。

如果需要指定安装的版本，可以在 pip 命令中指定版本号，例如：

```sh
pip install textlong==1.2.3
```

这里`1.2.3`是假设的一个版本号，你应该根据需要替换成你想要安装的确切版本。

## 使用 Project 创作长文

### 建议在 jupyter 环境中使用

### 在 Jupyter 中导入 textlong

#### 安装 JupyterLab

在使用 textlong 之前，首先需要确保你的环境中安装了 JupyterLab。JupyterLab 是一个交互式的开发环境，非常适合进行数据分析和机器学习项目。你可以通过以下命令安装 JupyterLab：

```sh
pip install jupyterlab
```

如果你使用的是 conda 环境，也可以使用 conda 命令进行安装：

```sh
conda install -c conda-forge jupyterlab
```

安装完成后，可以通过运行以下命令来启动 JupyterLab：

```sh
jupyter-lab
```

#### 建立笔记

启动 JupyterLab 后，你将看到一个 Web 界面。点击页面右上角的`New`按钮，选择`Python 3`来创建一个新的笔记。

#### 导入 textlong 包

在新的笔记中，首先需要导入 textlong 包。在进行导入之前，请确保已经按照前面的步骤正确安装了 textlong 包。以下是如何在 Jupyter 笔记中导入 textlong 包的示例：

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
p = Project(ChatZhipuAI(model="glm-4"), project_id="project")
p
```

这里`project_id`是你为 textlong 项目指定的唯一标识符。确保你使用的是正确的 API 模型名称和项目 ID。

通过上述步骤，你就可以在 JupyterLab 环境中使用 textlong 包来创作长文了。

### 创作提纲

在创作长篇文章时，使用 textlong 的提纲功能可以帮助你更好地组织和规划文章结构。以下是如何使用 textlong 创作提纲的详细步骤。

首先，你需要明确文章的主题、大纲和关键要素。在这个例子中，我们要创作的是一部 500 字的修仙小说，标题为《我修了个假仙》，主角是夏小兰，男一号是周成，每个章节都将以意外和打脸的线索推动情节。

接下来，使用 textlong 的`from_idea`方法来创建提纲。该方法接收三个参数：提纲文件的路径、文章创作的任务描述以及 prompt_id。以下是一个代码示例：

```python
task = "请帮我创作500字的修仙小说，标题为《我修了个假仙》，主角是夏小兰，男一号是周成，每一个章节都适用意外、打脸的线索推动。"
p.from_idea("提纲.md", task, prompt_id="OUTLINE")
```

在上面的代码中，"提纲.md"是生成的提纲文件的存储路径，task 是对文章创作任务的描述，prompt_id 用于标识这个提纲。

当你运行上述代码后，textlong 会根据你的任务描述自动生成一份提纲。提纲将包括小说的章节划分和每个章节的关键情节。你可以根据这个提纲来进行文章的扩写。

在提纲的基础上，你可以使用 textlong 的 Project 对象来逐步完成文章的创作。通过调用 Project 对象的相应方法，你可以让 AI 帮助你完成每个章节的细节描写，从而实现整篇小说的创作。

总之，使用 textlong 创作提纲可以大大提高你的写作效率，使你能够更加专注地构思情节和塑造角色，让创作过程变得更加轻松愉快。

### 文章扩写

基于提纲进行文章扩写是 textlong 的核心功能之一。它能够帮助作者根据已有的提纲框架，快速生成详细的文章内容。以下是如何使用 textlong 进行文章扩写的具体步骤。

首先，你需要有一个通过 textlong 生成的提纲文件，比如在我们的例子中，这个文件是“提纲.md”。然后，利用 textlong 的`from_outline`方法，你可以根据这个提纲文件生成文章的初稿。

基本的使用方法如上面的代码示例所示，你需要指定输出的文件名和输入的提纲文件名。例如：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input_file="提纲.md"
)
```

通过运行上述代码，textlong 将根据“提纲.md”中的结构，生成一篇名为“我修了个假仙人.md”的文章初稿。

然而，你可能希望对生成的文章进行微调，以更好地符合你的创作风格或文章需求。为此，你可以像下面这样调整`from_outline`方法的参数：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input_file="提纲.md",
    task="多使用人物细节、对话描写、打斗描写，减少抽象叙事"
)
```

在这个调整后的代码中，我们添加了一个额外的参数`task`，用于指导 AI 在生成文章时要特别关注的方面。这样，生成的文章将包含更多的人物细节、对话和打斗描写，同时减少抽象的叙述。

在使用`from_outline`方法时，你还可以根据需要调整其他参数，如`word_count`来控制生成的文章字数，或者`temperature`来调整生成内容的创意程度。

总之，通过这些步骤，你不仅能够基于提纲快速生成文章内容，还能够通过调整参数来优化和个性化生成的文章，使得最终的成品更加符合你的预期和创作要求。

### 引用素材管理

在创作长篇小说时，一个重要环节是生成和整理素材。textlong 工具提供了`from_idea`方法，可以帮助你快速生成特定主题的素材。比如，你可以通过以下代码生成关于小说人物的设定：

```python
task = "我要写一个修仙小说，主角是夏小兰，男一号是周成，请帮我设想一下这两个人的出身，要非常魔幻。"
p.from_idea("人物设定.md", task)
```

这段代码会根据你的要求，生成一份包含夏小兰和周成详细背景设定的文件“人物设定.md”。接下来，你可以使用这些素材来丰富你的文章。

当你想要在文章中使用这些素材时，可以通过`from_outline`方法中的`kg_files`参数来引用它们。如下示例：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input_file="提纲.md",
    task="多使用人物细节、对话描写、打斗描写，减少抽象叙事",
    kg_files=["人物设定.md"]
)
```

在这个例子中，`kg_files`参数指向了我们之前生成的“人物设定.md”。这样，textlong 在生成文章时，会自动参考这些素材，使得文章中的人物形象更加丰满，故事更加生动。

通过这种方式，你可以在创作过程中有效地管理素材，并确保它们被合理地融入文章中。这不仅提高了写作效率，还能使文章内容更加连贯和具有深度。

生成的人物设定可以作为素材，被引用到文章的相应部分，使故事更加引人入胜。

当素材准备好后，你可以将其整合到文章中，利用 textlong 的引用功能进行重新生成，确保整个故事的连贯性和统一性。

### 引用素材管理

<OUTLINE>
按下面思路整理并扩写：

指导如何生成素材。

生成素材的代码：

```python
task = "我要写一个修仙小说，主角是夏小兰，男一号是周成，请帮我设想一下这两个人的出身，要非常魔幻。"
p.from_idea("人物设定.md", task)
```

引用素材重新生成：

```python
p.from_outline(
    output_file="我修了个假仙人.md",
    input_file="提纲.md",
    task="多使用人物细节、对话描写、打斗描写，减少抽象叙事",
    kg_files=["人物设定.md"]
)
```
