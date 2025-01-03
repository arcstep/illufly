@auth @register @api-doc
Feature: 用户认证系统 - 注册模块
  """
  用户认证系统 - 注册模块 API 文档
  基础路径: /api/auth
  版本: 0.7
  最后更新: 2024-12-15
  负责人: @xuehongwei
  
  ## API 端点
  - POST /auth/register: 用户注册
    - 参数 (Form):
      - username: str, 必填, 用户名
      - password: str, 必填, 密码
      - email: str, 必填, 电子邮箱
      - invite_code: str, 可选, 邀请码
    - 返回:
      - success: bool, 操作是否成功
      - user_info: dict, 用户信息
        - user_id: str, 用户ID
        - username: str, 用户名
        - email: str, 电子邮箱
        - roles: List[str], 用户角色
        - is_active: bool, 是否激活
        - created_at: datetime, 创建时间
    - Cookie:
      - access_token: JWT访问令牌
      - refresh_token: JWT刷新令牌
    - 错误码:
      - 400: 参数验证失败
      - 500: 服务器内部错误

  ## 验证规则
  - 用户名:
    - 长度: 3-32个字符
    - 允许字符: 字母、数字、下划线
    - 不允许纯数字
  - 密码强度要求:
    - 最小长度: 8个字符
    - 必须包含: 大小写字母、数字、特殊字符
    - 不允许常见密码
  - 邮箱:
    - 标准邮箱格式
    - 域名必须有效
  - 邀请码:
    - 长度: 8-16个字符
    - 有效期: 24小时
    - 使用次数限制

  ## 安全措施
  - 密码加密存储: Argon2id
  - 防重放攻击: 注册请求去重
  - 频率限制: 每IP每小时最多10次注册尝试
  - 敏感信息脱敏
  """

  Background: 测试环境准备
    Given FastAPI 已经准备好
    And 清理测试数据

  @core @happy-path
  Scenario: [POST /auth/register] 基本用户注册
    Given 准备好用户表单
      | 字段     | 值                | 说明    |
      | username | mockuser         | 用户名  |
      | password | Test123!@#      | 密码     |
      | email    | mock@example.com | 邮箱    |
    When 提交用户注册请求
    Then 系统返回状态码 200
    And 返回成功响应

  @validation @error
  Scenario Outline: 注册参数验证
    Given 准备好用户表单
      | 字段       | 值              |
      | username  | <username>     |
      | password  | <password>     |
      | email     | <email>        |
    When 提交用户注册请求
    Then 系统返回状态码 400
    And 返回错误信息包含 "<error_message>"

    Examples: 无效的用户名
      | username | password    | email           | error_message                        |
      | a       | Test123!@#  | test@email.com  | 用户名长度必须在3到32个字符之间            |
      | ab#$    | Test123!@#  | test@email.com  | 用户名只能包含字母、数字和下划线            |

    Examples: 无效的密码
      | username | password  | email           | error_message                    |
      | testuser | 123      | test@email.com  | 密码长度必须至少为8个字符             |
      | testuser | password | test@email.com  | 密码必须包含至少一个大写字母           |

    Examples: 无效的邮箱
      | username | password    | email      | error_message    |
      | testuser | Test123!@# | invalid    | 邮箱格式无效      |
      | testuser | Test123!@# | @test.com  | 邮箱格式无效      |

  @duplicate @error
  Scenario: 注册重复用户名
    Given 准备好用户表单
      | 字段     | 值                |
      | username | duplicate_user   |
      | password | Test123!@#      |
      | email    | new@example.com |
    When 提交用户注册请求
    And 提交用户注册请求
    Then 系统返回状态码 400
    And 返回错误信息包含 "用户名已存在"

  @invite-code
  Scenario: 使用邀请码注册
    Given 准备好邀请码
      | 字段        | 值         |
      | invite_from | admin     |
      | invite_count | 2        |
    And 准备好用户表单
      | 字段        | 值                |
      | username    | mockuser         |
      | password    | Test123!@#      |
      | email       | mock@example.com |
      | invite_code | AUTO_FIND_VALID_CODE  |
    When 提交用户注册请求
    Then 系统返回状态码 200
    And 返回成功响应

  @invite-code @error
  Scenario: 使用无效邀请码
    Given 准备好用户表单
      | 字段        | 值                |
      | username    | mockuser         |
      | password    | Test123!@#      |
      | email       | mock@example.com |
      | invite_code | INVALID_CODE    |
    When 提交用户注册请求
    Then 系统返回状态码 400
    And 返回错误信息包含 "邀请码无效"

  """
  ## 实现注意事项

  ### 数据安全
  - 支持多种密码哈希算法
  - 实现密码历史记录
  - 邮箱地址加密存储
  - 关键操作使用事务

  ### 性能优化
  - 用户名索引优化
  - 邮箱查询缓存
  - 邀请码验证缓存
  - 注册流程异步处理

  ### 可用性保障
  - 支持注册失败重试
  - 邮箱验证容错处理
  - 友好的错误提示
  - 注册进度保存

  ### 监控指标
  - 注册成功率
  - 验证失败分布
  - 邀请码使用情况
  - 注册来源分析

  ### 运维支持
  - 提供注册数据导出
  - 支持批量邀请码生成
  - 注册策略动态配置
  - 提供运营数据分析
  """