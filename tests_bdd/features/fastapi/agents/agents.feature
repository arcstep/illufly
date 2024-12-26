@agents @api-doc
Feature: Agent智能助手管理
  """
  Agent管理系统 - 智能助手创建与管理
  基础路径: /api/agents
  版本: 0.8
  最后更新: 2024-03-20
  负责人: @xuehongwei

  ## API 端点
  - GET /agents: 获取Agent列表
    - 参数: 无
    - 返回:
      - success: bool
      - data: List[Dict]
    - 错误码:
      - 401: 未授权访问
      - 500: 服务器错误

  - POST /agents: 创建新Agent
    - 参数 (Form):
      - name: str, 必填, Agent名称
      - agent_type: str, 必填, Agent类型
      - description: str, 可选, Agent描述
      - vectordb_names: List[str], 可选, 关联知识库
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 400: 参数验证失败
      - 401: 未授权访问
      - 500: 服务器错误

  - GET /agents/{agent_name}: 获取Agent详情
    - 参数:
      - agent_name: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: Agent不存在
      - 401: 未授权访问

  - POST /agents/{agent_name}/stream: Agent对话
    - 参数:
      - agent_name: str, 路径参数
      - prompt: str, 查询参数
    - 返回:
      - EventSourceResponse
    - 错误码:
      - 404: Agent不存在
      - 401: 未授权访问
      - 500: 服务器错误

  - PATCH /agents/{agent_name}: 更新Agent配置
    - 参数 (Form):
      - description: str, 可选
      - vectordb_names: List[str], 可选
      - config: Dict, 可选
      - is_active: bool, 可选
    - 返回:
      - success: bool
      - data: Dict
    - 错误码:
      - 404: Agent不存在
      - 401: 未授权访问

  - DELETE /agents/{agent_name}: 删除Agent
    - 参数:
      - agent_name: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict
    - 错误码:
      - 404: Agent不存在
      - 401: 未授权访问

  # 功能概述
  实现智能助手(Agent)的全生命周期管理,支持创建、配置、使用和删除操作。

  ## 业务背景
  - 用户需要创建和管理多个不同类型的智能助手
  - 智能助手需要关联知识库以提供专业服务
  - 支持实时对话和流式响应

  ## 关键术语
  - Agent: 智能助手,可执行特定任务的AI模型
  - 知识库: 为Agent提供专业知识的向量数据库
  - 流式响应: 支持实时返回AI生成内容的SSE连接

  ## 安全考虑
  - Agent访问权限控制
  - 知识库数据隔离
  - 对话内容安全审计

  ## 相关需求
  - REQ-101: Agent基础管理
  - REQ-102: 知识库集成
  - REQ-103: 对话能力
  """

  Background: 测试环境准备
    Given FastAPI 已经准备好
    And 清理测试数据
    And 系统已有注册用户:
      | 字段     | 值              |
      | username | test_user       |
      | password | Test123!@#      |
      | email    | test@example.com|
      | roles    | ["user"]        |
    When 用户登录到设备

  @core @happy-path
  Scenario: 创建新的Agent
    """
    基础场景,创建一个新的Agent并验证其配置。

    注意事项:
    - Agent名称必须唯一
    - Agent类型必须有效
    - 知识库必须存在
    """
    When 用户创建新的Agent:
      | 字段         | 值           |
      | name         | test_agent   |
      | agent_type   | chat         |
      | description  | 测试助手     |
      | vectordb_names| []          |
    Then 创建应该成功
    And 返回的数据应包含:
      | 字段         | 类型         |
      | success      | boolean      |
      | data         | object       |
    And Agent应出现在用户的Agent列表中

  @core
  Scenario: 获取Agent列表
    Given 用户已创建以下Agent:
      | name      | type  | description |
      | agent_1   | chat  | 助手1      |
      | agent_2   | chat  | 助手2      |
    When 用户请求Agent列表
    Then 返回的列表应包含2个Agent
    And 每个Agent信息应包含:
      | 字段        | 类型    |
      | agent_name  | string  |
      | agent_type  | string  |
      | description | string  |
      | is_active   | boolean |

  @core
  Scenario: 更新Agent配置
    Given 存在名为"test_agent"的Agent
    When 用户更新Agent配置:
      | 字段         | 值           |
      | description  | 新的描述     |
      | is_active    | false        |
    Then 更新应该成功
    And Agent的配置应被更新为新值

  @core
  Scenario: 与Agent对话
    Given 存在名为"test_agent"的Agent
    When 用户发送消息"你好"
    Then 应建立SSE连接
    And 应收到Agent的回复

  @error
  Scenario Outline: Agent操作错误处理
    When 用户执行<操作>操作:
      | 参数    | 值        |
      | <参数>  | <参数值>  |
    Then 系统应返回<错误码>
    And 错误信息应包含"<错误描述>"

    Examples:
      | 操作   | 参数      | 参数值    | 错误码 | 错误描述        |
      | 创建   | name      | agent_1   | 400    | Agent已存在     |
      | 更新   | name      | not_exist | 404    | Agent不存在     |
      | 删除   | name      | not_exist | 404    | Agent不存在     |
      | 对话   | prompt    | ""        | 400    | 无效的输入      |

  """
  ## 实现注意事项

  ### 数据存储
  - Agent配置使用持久化存储
  - 支持配置版本管理
  - 实现数据备份机制

  ### 性能优化
  - Agent列表支持分页
  - 对话使用异步处理
  - 配置缓存机制

  ### 安全控制
  - 实现细粒度权限控制
  - 记录操作审计日志
  - 防止越权访问

  ### 监控告警
  - Agent状态监控
  - 异常对话检测
  - 性能指标采集

  ### 运维支持
  - 提供配置导入导出
  - 支持批量操作
  - 提供运行状态诊断
  """