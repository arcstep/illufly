# password_reset.feature
Feature: 密码重置
  作为系统用户
  我想在忘记密码时重置密码
  以重新获得账户访问权限

  Scenario: 请求重置密码
    When 用户请求重置密码:
      | Field  | Value             |
      | email  | test@example.com  |
    Then 系统应发送重置密码链接到用户邮箱
    And 返回成功响应

  Scenario: 验证重置密码令牌
    When 用户点击重置密码链接
    Then 系统应验证重置令牌的有效性
    And 允许用户设置新密码

  Scenario: 完成密码重置
    Given 用户持有有效的重置密码令牌
    When 用户设置新密码:
      | Field        | Value    |
      | new_password | Test123! |
    Then 系统应验证新密码强度
    And 更新用户密码
    And 使重置令牌失效
    And 返回成功响应