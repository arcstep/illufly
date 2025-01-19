# 模块规划

## *env 环境变量配置

## *mq 消息队列
- LocalService 队列服务：包含客户端
- ZmqServer 队列服务端

## *io/rocksdb：RocksDB
- IndexedRocksDB 支持索引
    - 支持 Faiss
        - ConceptMapRocksDB 支持概念图

## *io/faiss 向量索引
- Faiss 实现

## *io/concept 概念图管理
- ConceptMapsManager

## *model/llm 大模型对话服务：队列服务
- 系统提示语模板
- 消息格式管理
- 调用持久化

## *model/embeddings 向量模型服务：队列服务

## *agent 对话智能体：队列服务
- 支持提示语模板和上下文
- 连续对话
- 支持工具回调
- 检索和修订上下文

## *tools 工具服务：队列服务
- 基础工具定义
    - 读取知识
        - 读取网页
        - 读取本地文件

    - 使用对话智能体实现
        - 代码生成
        - 概念图生成

    - 使用复杂推理结构
        - ReAct
        - ReWOO
        - PlanAndExecute

    - 其他服务
        - 搜索服务
        - 图片识别服务
        - 生成图片服务
        - 代码执行沙盒

## *users 人类用户
- profile
- 刷新令牌

## *fastapi 面向队列的请求
- 登录授权
- 用户管理
- 服务调用
- 运行监控
- 服务管理
