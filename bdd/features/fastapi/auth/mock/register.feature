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
    Given Mock系统已启动
    And 用户管理模块正常运行
    And 清理测试数据

  @core @happy-path @wip
  Scenario: [POST /auth/register] 基本用户注册
    When 提交用户注册请求
      | 字段     | 值                | 说明     |
      | username | mockuser         | 用户名    |
      | password | Test123!@#      | 密码     |
      | email    | mock@example.com | 邮箱     |
    Then 系统返回状态码 200
    And 返回成功响应
    And 返回的用户信息包含
      | 字段        | 值                | 说明          |
      | username   | mockuser         | 用户名         |
      | email      | mock@example.com | 邮箱          |
      | roles      | ["user","guest"] | 用户角色列表    |
      | is_active  | true            | 账户激活状态    |
    And 密码应当被安全存储
    And 系统应设置认证Cookie
    And 记录注册审计日志

  @validation @error
  Scenario Outline: 注册参数验证
    When 提交用户注册请求
      | 字段     | 值     |
      | username | <username> |
      | password | <password> |
      | email    | <email>    |
    Then 系统返回状态码 400
    And 返回错误信息包含 "<error_message>"

    Examples: 无效的用户名
      | username | password    | email           | error_message |
      | a       | Test123!@#  | test@email.com  | 用户名长度不足 |
      | ab#$    | Test123!@#  | test@email.com  | 用户名包含非法字符 |

    Examples: 无效的密码
      | username | password  | email           | error_message |
      | testuser | 123      | test@email.com  | 密码不符合强度要求 |
      | testuser | password | test@email.com  | 密码不符合强度要求 |

    Examples: 无效的邮箱
      | username | password    | email      | error_message |
      | testuser | Test123!@# | invalid    | 邮箱格式无效 |
      | testuser | Test123!@# | @test.com  | 邮箱格式无效 |

  @duplicate @error
  Scenario: 注册重复用户名
    Given 存在用户名 "mockuser"
    When 提交用户注册请求
      | 字段     | 值                |
      | username | mockuser         |
      | password | Test123!@#      |
      | email    | new@example.com |
    Then 系统返回状态码 400
    And 返回错误信息包含 "用户名已存在"

  @invite-code
  Scenario: 使用邀请码注册
    When 提交用户注册请求
      | 字段        | 值                |
      | username    | mockuser         |
      | password    | Test123!@#      |
      | email       | mock@example.com |
      | invite_code | VALID_CODE      |
    Then 系统返回状态码 200
    And 返回成功响应

  @invite-code @error
  Scenario: 使用无效邀请码
    When 提交用户注册请求
      | 字段        | 值                |
      | username    | mockuser         |
      | password    | Test123!@#      |
      | email       | mock@example.com |
      | invite_code | INVALID_CODE    |
    Then 系统返回状态码 400
    And 返回错误信息包含 "Invalid invite code"

  """
  ## 实现注意事项

  ### 数据安全
  - 使用 Argon2id 进行密码哈希
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