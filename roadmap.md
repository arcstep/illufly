# 一、开发计划

## 1. 创作方法

**项目：**

- 提取 extract
- 创意 from_idea
- 分段 from_chunk
- 扩写 from_outline

**脚本：**

- 保存脚本
- 执行脚本

**模板：**

- 打包项目模板
- 发布项目模板

## 2. 提示语管理

- 引用提示语
- 缓存提示语

- 打包提示语
- 发布提示语

## 3. 项目

- 项目位置
- 创作输出

## 4. FastAPI 分享

- 项目列表
- 分享网页
- 一键直出
- 项目模板查询
- 提示语查询

## 5. QA

- 加载 本地文件：docx / pdf /md / txt
- 加载 QA-Excel
- 为项目做 RAG
- 为用户做 RAG
- 支持用户共享资料的 RAG

## 6. Agent

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

## 7. 分享

- 导出 MD
- 导出 HTML
- 导出 Jupyter
- 导出 Word
- 导出 PDF

- 在线分享 HTML
