# admin_user_management.feature
Feature: 管理员用户管理
  作为系统管理员
  我想管理系统用户
  以维护用户账户和权限

  Background:
    Given 当前用户具有管理员权限

  Scenario: 获取用户列表
    When 管理员请求获取用户列表
    Then 系统应返回所有用户信息列表
    And 每个用户信息应包含:
      | Field       | Type    |
      | user_id     | string  |
      | username    | string  |
      | email       | string  |
      | roles       | array   |
      | is_active   | boolean |
      | is_locked   | boolean |

  Scenario: 更新用户角色
    When 管理员更新指定用户的角色:
      | Field    | Value           |
      | user_id  | <user_id>       |
      | roles    | ["USER","ADMIN"] |
    Then 系统应更新用户角色
    And 返回成功响应

  Scenario: 锁定用户账户
    When 管理员锁定指定用户账户:
      | Field    | Value     |
      | user_id  | <user_id> |
      | reason   | 违规操作   |
    Then 系统应锁定该用户账户
    And 记录锁定原因
    And 返回成功响应

  Scenario: 解锁用户账户
    When 管理员解锁指定用户账户:
      | Field    | Value     |
      | user_id  | <user_id> |
    Then 系统应解锁该用户账户
    And 返回成功响应

  Scenario: 管理员重置用户密码
    When 管理员为指定用户重置密码:
      | Field        | Value     |
      | user_id      | <user_id> |
      | new_password | Test123!  |
    Then 系统应验证新密码强度
    And 更新用户密码
    And 标记用户下次登录需要修改密码
    And 返回成功响应

  Scenario: 删除用户账户
    When 管理员删除指定用户账户:
      | Field    | Value     |
      | user_id  | <user_id> |
    Then 系统应软删除该用户账户
    And 保留用户历史数据
    And 返回成功响应