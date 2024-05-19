WRITING_HELP = """
# `textlong`包使用指南

`textlong`是一个python包, 基于大语言模型的AI工作, 可用于长文写作、长文理解等任务。

## `WritingTask`模块。

`WritingTask`模块专门负责生成任务。
其工作方式是将写作任务拆解为写作提纲和子任务，再执行每个子任务，最后合成完整文本。

### 写作功能

#### 创建写作项目

```python
from textlong import 
```

#### invoke方法
最灵活的方法是调用WritingTask的invoke方法。

第一步，你应当准备好访问大语言模型所需的APIKEY，你可以选择你喜欢的任何LLM,如ChatGPT、智谱AI等，
默认支持的是智谱AI。

第二步，你要在代码中创建`WritingTask`对象。

**使用默认的智谱AI:**

```python
from textlong import WritingTask
task = WritingTask()
```

**使用ChatGPT:**

```python
from textlong import WritingTask
from langchain_openai import ChatOpenAI

task = WritingTask(llm=ChatOpenAI())
```

第三步，你要调用`invoke`方法，并传递指令。

以下是一个简单的代码示范，使用task命令让AI生成800字的信；
紧接着，代码ok命令将生成的内容保存。

```python
task.invoke("task 致孩子的一封信, 800字")
task.invoke("ok")
```
#### auto_write方法
使用auto_write方法可以在生成任务后自动执行ok命令，自动生成和确认所有子任务，直至全文创作完毕。

```python
task.auto_write("task 致孩子的一封信, 800字")
```

#### repl_write方法
如果你希望精细控制，还可以使用repl_write方法。

```python
task.repl_write("task 致孩子的一封信, 800字")
```

repl_write会进入一个控制台循环，这通常是在`Jupyter Notes`或命令行终端的环境中。
在控制台循环中，你可以不断输入`ok`指令，直至完成，也可以选择其他指令，执行重新生成、修改扩写指南等任务。

### invoke和repl中可用的命令清单

这些命令并非shell脚本，而是在WritingTask的invoke方法中的参数。
一般的使用方法例如：`writingTaskObj.invoke("<命令名称> <可选的参数>")`

**注意: [ ] 表示该命令尚未完成开发; [x] 表示已经完成开发、可以正常使用。**

- [x] `help` 向AI寻求帮助：优化提示语为对指令的说明
- [x] `state` 当前节点状态数据
- [x] `title [可选的新标题]` 读取或修改标题
- [x] `words_advice [可选的字数建议]` 读取或修改字数建议
- [x] `howto [可选的新扩写指南说明]` 读取或修改扩写指南
- [x] `summarise [可选的新段落摘要]` 读取或修改段落摘要
- [x] `text [可选的新的段落文本]` 读取或修改段落文本
- [x] `content` 读取当前节点所有的属性数据
- [x] `nodes` 所有节点数据
- [x] `task [请求AI生成的任务描述，默认为“请继续”]` 请求AI生成内容
- [x] `ok` 将AI生成的内容保存到节点中
- [x] `memory` 提取当前内容节点的AI对话历史
- [x] `outlines` 从根内容开始遍历当前的大纲结构，返回标题、扩写指南等内容
- [x] `texts` 已完成文字成果汇总
- [ ] `export txt` 导出文字成果到TXT文件到默认的存储文件夹
- [ ] `export docx` 导出文字成果到Word文件到默认的存储文件夹
- [ ] `export md` 导出文字成果到MD文件到默认的存储文件夹
- [ ] `export` 从内存导出JSON结构到默认的存储文件夹
- [ ] `import` 从到默认的存储文件夹导入JSON文件到内存
- [ ] `load [filename.*]` 导入外部文件为知识库
- [ ] `quit` 退出 repl 循环

"""