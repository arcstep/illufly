# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['langchain_chinese', 'langchain_chinese.zhipuai']

package_data = \
{'': ['*']}

install_requires = \
['setuptools>=69.1.0,<70.0.0', 'zhipu>=1.0.1,<2.0.0']

setup_kwargs = {
    'name': 'langchain_chinese',
    'version': '0.1.0',
    'description': 'prepare some firendly tool for Chinese LLMs and langchain',
    'long_description': '# langchain_chinese\n提供中文大语言模型和中文友好的 langchain 工具\n\n## 安装\n\n你可以从github上直接下载包：\n```\npip install git+https://github.com/arcstep/langchain_chinese.git@v0.1\n```\n\n然后在 langchain 项目中引入：\n```\nfrom langchain_chinese import ZhipuaiChat\n```\n\n## 在 JupyterLab 中运行示例代码\n项目源码中 /notes 目录有一些示例代码，可以尝试在 Jupyter 中运行。\n\n如果不熟悉 Jupyter 环境，下面是一个简单的指南。\n\n### 准备 Python 3.9 版本以上的环境\n建议使用虚拟环境，如 pyenv、conda或poetry，这里以 pyenv + poetry为例。\n\n### 确保安装 JupyterLab\n\n要安装 JupyterLab，你可以使用 Python 的包管理器 pip。在你的命令行中运行以下命令：\n\n```bash\npip install jupyterlab\n```\n\n如果你正在使用一个特定的 Python 虚拟环境，或者你想要为一个特定的 Python 项目安装 JupyterLab，你应该在那个环境中运行这个命令。\n\n如果你正在使用 Poetry 来管理你的 Python 项目，你可以使用以下命令来安装 JupyterLab：\n\n```bash\npoetry add jupyterlab\n```\n\n安装完成后，你可以通过在命令行中运行 `jupyter lab` 来启动 JupyterLab。\n\n### 在 JupyterLab 中使用专门的 ipykernel\n\n要在 Poetry 环境中创建一个 JupyterLab 可用的 kernel，你需要先确保你已经安装了 `ipykernel` 包。你可以使用以下命令在你的 Poetry 环境中安装 `ipykernel`：\n\n```bash\npoetry add ipykernel\n```\n\n然后，你可以使用以下命令在你的 Poetry 环境中创建一个新的 Jupyter kernel：\n\n```bash\npoetry run python -m ipykernel install --user --name=langchain_chinese_kernel\n```\n\n在这个命令中，`langchain_chinese_kernel` 是你的新 kernel 的名称，你可以根据你的需要更改它。\n\n现在，当你启动 JupyterLab 时，你应该能在 kernel 列表中看到你的新 kernel。你可以通过选择这个新 kernel 来在你的 Poetry 环境中运行 Jupyter notebook。',
    'author': 'arcstep',
    'author_email': '43801@qq.com',
    'maintainer': 'None',
    'maintainer_email': 'None',
    'url': 'None',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.9,<4.0',
}


setup(**setup_kwargs)

