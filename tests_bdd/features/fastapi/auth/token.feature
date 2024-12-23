@auth @token @api-doc
Feature: 令牌管理系统(Mock版本)
  """
  令牌管理系统 API 文档
  基础路径: /api/auth
  版本: 0.7
  最后更新: 2024-12-15
  负责人: @xuehongwei

  ## API 端点
  - POST /auth/refresh-token: 刷新访问令牌
    - 参数 (Form):
      - refresh_token: str, 必填, 刷新令牌
    - 返回:
      - success: bool
      - access_token: str, 新的访问令牌
      - refresh_token: str, 新的刷新令牌
    - 错误码:
      - 400: 无效的令牌
      - 401: 令牌过期/未授权
      - 500: 服务器错误

  - POST /auth/revoke-token: 撤销用户令牌
    - 参数 (Form):
      - username: str, 必填, 用户名
    - 权限要求: admin
    - 返回:
      - success: bool
      - message: str
    - 错误码:
      - 400: 用户不存在
      - 403: 权限不足
      - 500: 服务器错误

  - POST /auth/revoke-access-token: 撤销访问令牌
    - 参数 (Form):
      - username: str, 必填, 用户名
    - 权限要求: admin
    - 返回:
      - success: bool
      - message: str
      - username: str

  ## 安全考虑
  - 令牌操作需要并发安全
  - 支持集群环境下的令牌同步
  - 所有操作需要记录审计日志
  """

  Background: 
    Given 初始化测试环境
    And 清空令牌存储
    And 准备测试用户数据:
      | username | user_id | roles      |
      | admin    | admin1  | ["admin"]  |
      | user1    | user1   | ["user"]   |

  @core @refresh
  Scenario: [POST /auth/refresh-token] 基础令牌刷新
    When 用户在设备A提供正确的登录信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
    When 发起令牌刷新请求
    Then 系统应返回状态码 200
    And 响应中包含:
      | 字段           | 类型   | 说明        |
      | success       | bool   | true        |
      | access_token  | string | 新访问令牌   |
      | refresh_token | string | 新刷新令牌   |

  @core @refresh @error
  Scenario Outline: [POST /auth/refresh-token] 异常令牌刷新
    Given 初始化测试环境
    And 清空令牌存储
    And 准备测试用户数据
      | username | user_id | roles     |
      | admin    | admin1  | ["admin"] |
      | user1    | user1   | ["user"]  |
    Given <场景>
    When 发起令牌刷新请求
    Then 系统应返回状态码 <状态码>
    And 响应中包含错误信息 "<错误消息>"

    Examples: 异常场景
      | 场景                   | 状态码 | 错误消息                 |
      | 用户持有过期的刷新令牌    | 401   | 令牌已过期               |
      | 用户持有无效的刷新令牌    | 400   | 无效的刷新令牌格式         |
      | 用户持有格式错误的刷新令牌  | 400   | 无效的刷新令牌格式         |
      | 用户持有已使用的刷新令牌   | 401   | 令牌已在其他设备上使用      |

  @security @revoke @admin
  Scenario: [POST /auth/revoke-token] 管理员撤销用户令牌
    Given 管理员已登录
    And 存在以下活跃令牌:
      | user_id | device_id | token_type    |
      | user1   | dev1      | access_token  |
      | user1   | dev2      | refresh_token |
    When 管理员请求撤销用户 "user1" 的所有令牌
    Then 系统应返回状态码 200
    And 响应中包含:
      | 字段     | 值                              |
      | success  | true                           |
      | message  | "Successfully revoked tokens"  |
    And 该用户的所有令牌应被标记为无效
    And 审计日志应记录此操作:
      | 字段      | 值                    |
      | action   | "revoke_all_tokens"   |
      | admin_id | "admin1"              |
      | user_id  | "user1"               |

  """
  ## 实现注意事项
  - 所有令牌操作需要考虑并发安全
  - 令牌撤销需要支持集群环境
  - 需要实现令牌状态的持久化存储
  - 审计日志需要包含详细的操作信息
  - 令牌验证需要使用缓存提升性能
  - 支持令牌黑名单机制
  """