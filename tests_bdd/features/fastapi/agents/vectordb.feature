@vectordbs @api-doc
Feature: 向量知识库管理
  """
  向量知识库管理系统 - 知识库的创建与管理
  基础路径: /api/vectordbs
  版本: 0.8
  最后更新: 2024-12-24
  负责人: @xuehongwei

  ## API 端点
  - GET /vectordbs: 获取知识库列表
    - 参数: 无
    - 返回:
      - List[str]: 知识库名称列表
    - 错误码:
      - 401: 未授权访问
      - 500: 服务器错误

  - POST /vectordbs: 创建新知识库
    - 参数 (Form):
      - name: str, 必填, 知识库名称
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 400: 参数验证失败/知识库已存在
      - 401: 未授权访问

  - GET /vectordbs/{db_name}: 获取知识库详情
    - 参数:
      - db_name: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 401: 未授权访问

  - PATCH /vectordbs/{db_name}: 更新知识库配置
    - 参数 (Form):
      - db_type: str, 可选
      - top_k: int, 可选
      - config: Dict[str, Any], 可选
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 401: 未授权访问

  - DELETE /vectordbs/{db_name}: 删除知识库
    - 参数:
      - db_name: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 401: 未授权访问

  # 功能概述
  实现向量知识库的全生命周期管理,支持创建、配置、查询和删除操作。

  ## 业务背景
  - 用户需要管理多个知识库来支持不同的Agent
  - 知识库需要支持不同的向量数据库类型
  - 知识库配置需要支持动态调整

  ## 关键术语
  - 向量知识库: 存储文档向量的数据库
  - top_k: 相似度查询返回的最大结果数
  - 配置项: 特定向量数据库类型的专用配置

  ## 安全考虑
  - 知识库访问权限控制
  - 数据隔离
  - 操作审计
  """

  Background: 测试环境准备
    Given FastAPI 已经准备好
    And 清理测试数据
    And 系统已有测试用户:
      | 字段     | 值              |
      | username | test_user       |
      | password | Test123!@#      |
      | email    | test@example.com|
      | roles    | ["user"]        |
    And 用户已登录系统

  @core @happy-path
  Scenario: 创建新的知识库
    """
    基础场景,创建一个新的知识库并验证其配置。

    注意事项:
    - 知识库名称必须唯一
    - 名称格式验证
    - 用户权限验证
    """
    When 用户创建新的知识库:
      | 字段  | 值            |
      | name  | test_vectordb |
    Then 创建应该成功
    And 返回的数据应包含:
      | 字段    | 类型    |
      | success | boolean |
      | data    | object  |
    And 知识库应出现在用户的知识库列表中

  @core
  Scenario: 获取知识库列表
    Given 用户已创建以下知识库:
      | name          |
      | test_db_1     |
      | test_db_2     |
    When 用户请求知识库列表
    Then 返回的列表应包含2个知识库
    And 列表应包含["test_db_1", "test_db_2"]

  @core
  Scenario: 更新知识库配置
    Given 存在名为"test_vectordb"的知识库
    When 用户更新知识库配置:
      | 字段    | 值     |
      | db_type | milvus |
      | top_k   | 5      |
    Then 更新应该成功
    And 知识库的配置应被更新为新值

  @core
  Scenario: 获取知识库详情
    Given 存在名为"test_vectordb"的知识库
    When 用户请求知识库"test_vectordb"的详情
    Then 返回应该成功
    And 返回的数据应包含:
      | 字段    | 类型    |
      | db_type | string  |
      | top_k   | integer |
      | config  | object  |

  @core
  Scenario: 删除知识库
    Given 存在名为"test_vectordb"的知识库
    When 用户删除知识库"test_vectordb"
    Then 删除应该成功
    And 知识库列表中不应包含"test_vectordb"

  @error
  Scenario Outline: 知识库操作错误处理
    When 用户执行<操作>操作:
      | 参数    | 值        |
      | <参数>  | <参数值>  |
    Then 系统应返回<错误码>
    And 错误信息应包含"<错误描述>"

    Examples:
      | 操作   | 参数    | 参数值        | 错误码 | 错误描述        |
      | 创建   | name    | test_db_1     | 400    | 知识库已存在     |
      | 更新   | db_name | not_exist     | 404    | 知识库不存在     |
      | 删除   | db_name | not_exist     | 404    | 知识库不存在     |
      | 查询   | db_name | not_exist     | 404    | 知识库不存在     |

  """
  ## 实现注意事项

  ### 数据存储
  - 知识库元数据使用关系型数据库
  - 向量数据使用专门的向量数据库
  - 支持配置备份和恢复

  ### 性能优化
  - 知识库列表缓存
  - 配置更新原子性
  - 异步删除机制

  ### 安全控制
  - 实现多租户隔离
  - 记录操作日志
  - 防止越权访问

  ### 监控告警
  - 知识库容量监控
  - 操作性能监控
  - 异常访问告警

  ### 运维支持
  - 提供数据迁移工具
  - 支持批量操作
  - 提供运行状态诊断
  """