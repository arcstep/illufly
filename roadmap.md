# 一、开发计划

## 1. 创作方法

**方法：**

- 创意 IDEA
- 大纲 OUTLINE
- 扩写 FROM_OUTLINE
- 细化大纲 OUTLINE_FROM_OUTLINE

- 支持多个 input
- 支持多个 knowledge

- 整体
- 按大纲拆分

- 支持在流式输出中将日志和最终结果分离
- 支持可定制的颜色打印
- 支持 fake 模式
- 支持 verbose 模式
- 支持 config 参数 prev_k 和 next_k 控制参考的上下文长度

_TODO:更多方法_

- 翻译
- 仿写
- 摘要
- 提炼

_TODO:输入输出模式_

- 1 -> 1
- 1 -> n
- n -> 1

_TODO:生成核心_

- 支持使用链和智能体替代 LLM 执行生成任务
- 支持开源模型

_TODO:并行输出_

- 按多个 LLM 同时输出
- 按多份提示语模板同时输出

**项目：**

_TODO:_

- 创意 IDEA
- 大纲 OUTLINE
- 扩写 FROM_OUTLINE
- 细化大纲 OUTLINE_FROM_OUTLINE

**脚本：**

- 保存脚本
- 执行脚本

**提示语模板：**

- 从包中提取模板，并保存到本地
- 从内存提取模板，并保存到本地

_TODO:_

- 从 git 项目提取模板，并保存到本地
- 项目模板清单分享（基于 Git 服务器）

## 2. FastAPI 分享

- 项目列表
- 分享网页
- 一键直出
- 项目模板查询
- 提示语查询

## 3. QA

- 加载 本地文件：docx / pdf /md / txt
- 加载 QA-Excel
- 为项目做 RAG
- 为用户做 RAG
- 支持用户共享资料的 RAG

## 4. Agent

**支持定义工具：**

- 基于查询范围（文件、项目等）配置 RAG 工具
- 基于数据查询（SQL）配置数据分析工具

**自定义智能体执行器：**

- 基于工具辅助文档内容生成（由大模型推理结果决定是否使用工具）
- 支持多种智能体风格：Tools-Calling、ReAct、CoT
- 可无缝嵌入到写作过程中（支持流反馈）

**支持在其他场景中集成：**

- 作为 RAG Runnable 被集成：RAG 查询
- 作为 QA 工具中被集成：Tools-Calling、ReAct、CoT、langgraph 应用

## 5. 分享

- 导出 MD
- 导出 HTML
- 导出 Jupyter
- 导出 Word
- 导出 PDF

- 在线分享 HTML

## 6. 配置管理

**根文件夹配置**

- "TEXTLONG_ROOT": "",

**提示语文件夹**

- "TEXTLONG_PROMPTS": "**PROMPTS**",

**项目文件夹**

- "TEXTLONG_LOGS": "**LOG**",
- "TEXTLONG_SHARE": "**SHARE**",
- "TEXTLONG_DOCS": "**DOCS**",
- "TEXTLONG_QA": "**QA**",

**项目文件**

- "TEXTLONG_CONFIG_FILE": "project_config.yml",
- "TEXTLONG_SCRIPT_FILE": "project_script.yml",

**对话历史**

- "TEXTLONG_MEMORY_HISTORY": "**MEMORY_HISTORY**",

**用户个人文件夹**

- "TEXTLONG_DEFAULT_SESSION": "default",
- "TEXTLONG_DEFAULT_USER": "default_user",

**公共用户**

- "TEXTLONG_PUBLIC": "",
