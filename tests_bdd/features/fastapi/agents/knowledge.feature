@knowledge @api-doc
Feature: 知识条目管理
  """
  知识条目管理系统 - 知识的创建、查询与管理
  基础路径: /api/vectordbs/{db_name}/knowledge
  版本: 0.8
  最后更新: 2024-03-20
  负责人: @xuehongwei

  ## API 端点
  - GET /knowledge: 获取知识列表
    - 参数 (Query):
      - page: int, 页码(>=1)
      - page_size: int, 每页数量(1-100)
      - sort_by: str, 排序字段(id|summary|source|tags)
      - reverse: bool, 是否倒序
      - tags: List[str], 标签过滤
      - match_all_tags: bool, 是否匹配所有标签
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 401: 未授权访问

  - POST /knowledge: 创建新知识
    - 参数 (Form):
      - content: str, 必填, 知识内容
      - tags: List[str], 可选, 标签列表
      - summary: str, 可选, 摘要
      - source: str, 可选, 来源
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 400: 参数验证失败
      - 500: 服务器错误

  - GET /knowledge/{knowledge_id}: 获取知识详情
    - 参数:
      - knowledge_id: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识不存在

  - PUT /knowledge/{knowledge_id}: 更新知识
    - 参数 (Form):
      - content: str, 可选, 知识内容
      - tags: str, 可选, 标签(逗号分隔)
      - summary: str, 可选, 摘要
      - source: str, 可选, 来源
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识不存在
      - 400: 更新失败

  - DELETE /knowledge/{knowledge_id}: 删除知识
    - 参数:
      - knowledge_id: str, 路径参数
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识不存在

  - GET /knowledge/search: 搜索知识
    - 参数 (Query):
      - query: str, 必填, 搜索查询
      - limit: int, 结果数量限制(1-100)
    - 返回:
      - success: bool
      - data: Dict[str, Any]
    - 错误码:
      - 404: 知识库不存在
      - 500: 搜索失败

  # 功能概述
  实现知识条目的全生命周期管理,支持创建、查询、更新、删除和搜索操作。

  ## 业务背景
  - 用户需要管理大量结构化和非结构化知识
  - 支持知识的多维度检索和筛选
  - 提供相似度搜索能力
  """

  Background: 测试环境准备
    Given FastAPI 已经准备好
    And 清理测试数据
    And 系统已有测试用户:
      | 字段     | 值              |
      | username | test_user       |
      | password | Test123!@#      |
    And 用户已登录系统
    And 存在知识库"test_db"

  @core @happy-path
  Scenario: 创建新的知识条目
    When 用户在知识库"test_db"中创建知识:
      | 字段     | 值                    |
      | content  | 这是一条测试知识       |
      | tags     | ["测试", "示例"]      |
      | summary  | 测试知识摘要          |
      | source   | 单元测试              |
    Then 创建应该成功
    And 返回的数据应包含:
      | 字段    | 类型    |
      | id      | string  |
      | message | string  |

  @core
  Scenario: 分页获取知识列表
    Given 知识库"test_db"中存在多条知识
    When 用户请求知识列表:
      | 字段        | 值     |
      | page        | 1      |
      | page_size   | 10     |
      | sort_by     | id     |
      | reverse     | false  |
    Then 返回应该成功
    And 返回的数据应包含分页信息:
      | 字段        | 类型    |
      | total       | integer |
      | items       | array   |
      | page        | integer |
      | page_size   | integer |

  @core
  Scenario: 按标签筛选知识
    Given 知识库"test_db"中存在带标签的知识
    When 用户按标签筛选:
      | 字段           | 值            |
      | tags           | ["测试"]      |
      | match_all_tags | true          |
    Then 返回的知识列表应只包含指定标签的知识

  @core
  Scenario: 更新知识内容
    Given 知识库"test_db"中存在ID为"test_id"的知识
    When 用户更新该知识:
      | 字段    | 值              |
      | content | 更新后的内容     |
      | tags    | 新标签1,新标签2  |
    Then 更新应该成功
    And 知识内容应被更新

  @core
  Scenario: 相似度搜索
    Given 知识库"test_db"中存在多条知识
    When 用户执行搜索:
      | 字段   | 值              |
      | query  | 测试查询内容     |
      | limit  | 5              |
    Then 搜索应该成功
    And 返回结果应按相关度排序

  @error
  Scenario Outline: 知识操作错误处理
    When 用户执行<操作>操作:
      | 参数    | 值        |
      | <参数>  | <参数值>  |
    Then 系统应返回<错误码>
    And 错误信息应包含"<错误描述>"

    Examples:
      | 操作   | 参数         | 参数值    | 错误码 | 错误描述        |
      | 创建   | content      |           | 400    | 内容不能为空     |
      | 更新   | knowledge_id | not_exist | 404    | 知识不存在      |
      | 删除   | knowledge_id | not_exist | 404    | 知识不存在      |
      | 搜索   | query        |           | 400    | 查询不能为空     |

  """
  ## 实现注意事项

  ### 数据处理
  - 知识内容的向量化处理
  - 标签规范化和索引
  - 大文本存储优化

  ### 性能优化
  - 搜索结果缓存
  - 异步向量计算
  - 批量操作支持

  ### 安全控制
  - 内容安全审核
  - 访问权限控制
  - 操作日志记录

  ### 监控告警
  - 搜索性能监控
  - 存储容量监控
  - 异常访问检测

  ### 运维支持
  - 知识导入导出
  - 向量重建工具
  - 数据一致性检查
  """