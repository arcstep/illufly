Feature: 令牌管理
  作为已登录用户
  我想管理我的认证令牌
  以便维持安全的会话状态

  Background:
    Given 系统中存在已登录用户

  Scenario: 成功刷新令牌
    Given 用户持有有效的刷新令牌
    When 用户请求刷新令牌:
      | Field         | Value           |
      | refresh_token | <valid_token>   |
    Then 系统应验证刷新令牌
    And 使旧的刷新令牌失效
    And 生成新的访问令牌和刷新令牌
    And 返回成功响应，包含:
      | Field         | Type    |
      | success       | boolean |
      | access_token  | string  |
      | refresh_token | string  |
    And 更新认证Cookie

  Scenario: 刷新令牌失败 - 无效的令牌格式
    When 用户提供格式错误的刷新令牌
    Then 系统应返回400错误
    And 错误信息应说明令牌格式无效

  Scenario: 刷新令牌失败 - 令牌已过期
    When 用户提供已过期的刷新令牌
    Then 系统应返回401未授权错误
    And 错误信息应说明令牌已过期

  Scenario: 成功注销
    When 用户请求注销
    Then 系统应清除用户的认证Cookie
    And 移除用户的所有令牌
    And 返回成功响应

  Scenario: 用户撤销当前设备令牌
    When 用户请求撤销当前设备的令牌
    Then 系统应移除用户当前设备的令牌
    And 返回成功响应
    And 强制用户在该设备上重新登录

  Scenario: 用户撤销所有设备令牌
    When 用户请求撤销自身的所有令牌
    Then 系统应移除用户的所有令牌
    And 返回成功响应
    And 强制用户在所有设备上重新登录

  Scenario: 管理员撤销用户令牌
    Given 当前用户具有管理员权限
    When 管理员请求撤销指定用户的所有令牌:
      | Field    | Value    |
      | username | testuser |
    Then 系统应移除该用户的所有令牌
    And 返回成功响应
    And 响应信息应包含被操作的用户名

  Scenario: 管理员撤销访问令牌
    Given 当前用户具有管理员权限
    When 管理员请求撤销指定用户的访问令牌:
      | Field    | Value    |
      | username | testuser |
    Then 系统应移除该用户的访问令牌
    And 返回成功响应
    And 响应信息应包含被操作的用户名

  Scenario: 管理员暂时冻结用户
    Given 当前用户具有管理员权限
    When 管理员请求暂时冻结指定用户:
      | Field    | Value    |
      | username | testuser |
    Then 系统应暂时冻结该用户的账户
    And 返回成功响应
    And 响应信息应包含被操作的用户名

  Scenario: 撤销令牌失败 - 权限不足
    Given 当前用户不具有管理员权限
    When 用户尝试撤销他人的令牌
    Then 系统应返回403禁止访问错误
    And 错误信息应说明权限不足

  Scenario: 撤销令牌失败 - 用户不存在
    Given 当前用户具有管理员权限
    When 管理员尝试撤销不存在用户的令牌
    Then 系统应返回400错误
    And 错误信息应说明用户不存在