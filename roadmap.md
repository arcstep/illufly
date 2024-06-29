# 一、开发计划

## 1. 创作方法

**创作方法：**

- 创意 idea
- 大纲 outline
- 扩写 from_outline
- 细化大纲 outline_from_outline

- 支持多个 input，合并为一个上下文
- 支持多个 knowledge，合并为一个知识上下文

- 按整体作为任务
- 按大纲拆分任务

**项目管理：**

- 写作方法: idea, outline, from_outline ...
- 本地提示语: hub.load_prompt, hub.save_prompt, hub.clone_prompt
- 项目恢复: init, save_project
- 命令历史: load_commands, load_history
- 批处理: save_script, load_script, run_script
- 版本恢复: checkout
- 其他指令：session, save_as

**提示语模板：**

- 克隆提示语：clone_prompt
- 从代码构建提示语：save_prompt
- 手动编辑提示语
- 支持模板继承

**作为 SDK 使用：**

- 支持在流式输出中将日志和最终结果分离
- 支持可定制的颜色打印
- 支持 fake 模式
- 支持 verbose 模式
- 支持工程封装：将模型和 base_folder 封装在 Project

**作为 Chain 使用：**

- 支持 QA 链：可选记忆体，可动态构建文本嵌入
- 支持写作链：将 SDK 方法封装为 langfuse 可直接使用的 Runnable

**更多提示语模板：**

- 翻译
- 仿写
- 摘要
- 提炼
- 提炼概念
- 提炼知识三元组

**RAG 能力集成：**

- 加载 本地文件：docx / pdf /md / txt / xlsx
- 加载 QA-Excel：支持 QA 和普通 xls 文本
- 支持从多个目录加载

- 文本嵌入缓存和加载
- 支持按嵌入模型各自缓存
- 支持基于 redis 的缓存

- 支持记忆：基于内存、基于文件

- 支持`QA`元数据查询
- 支持`概念`元数据查询
- 支持`知识三元组`元数据关联查询

- 生成 QA 文档：设定 Q 和 A 的标题层次，以及 QA 分割线
- 从已有文档提炼资料：摘要、概念、实体、流程、三元组、QA

- 从 QA 结果作为生成文档的 knowledge

**Jupuyter 笔记**

- 启动模板：大模型配置、QA 应用和项目创作的 python 工具包
- 快速启动：零代码直接可用和简洁函数
- 支持命令行：结合启动模板，快速启动 Jupyter 环境

## 2. 跟踪和评估

**项目配置：**

- 项目配置文件
- 项目脚本文件
- 基于 redis 管理项目配置
- 基于 redis 管理项目脚本

**项目日志：**

- 生成日志
- 基于 redis 保存日志

**生成跟踪：**

- 保存输入和输出历史记录：输入参数、输出结果、提示语参数、大模型参数、token 使用
- 大模型和输出结果：评估指令跟随状况
- 提示语版本和输出结果：评估指令控制能力
- 输入参数和输出结果：评估指令工程效果
- 大模型 Token 跟踪：统计 Token 消耗

**生成评估：**

- 平行输入：按大模型参数、提示语版本、输入参数等
- 平行输出：每个评估一个输出标签文件夹
- 质量标注：对所有平行输出打标签
- 生成约束测试：对齐国内法律法规、道德规范

## 3. FastAPI

- 项目列表
- 项目生成
- 分享网页
- 提示语模板
- session 管理

## 4. QA

- 加载 本地文件：docx / pdf /md / txt / xlsx
- 加载 QA-Excel：支持 QA 和普通 xls 文本
- 支持从多个文件夹加载
- 支持文本嵌入缓存
- 支持记忆：基于内存、基于文件
- 支持按用户加载

- 支持文本拆分
- 支持 QA 查询
- 支持概念查询
- 支持知识三元组关联查询

- 从 parquet 查询数据并分析
- 从 xls 查询数据并分析
- 从 SQL 查询数据并分析
