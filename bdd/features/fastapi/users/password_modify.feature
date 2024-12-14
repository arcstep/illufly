# password_management.feature
Feature: 密码管理
  作为系统用户
  我想管理我的密码
  以确保账户安全

  Background:
    Given 系统中存在已注册用户

  Scenario: 修改个人密码
    When 用户修改自己的密码:
      | Field         | Value     |
      | old_password  | oldpass   |
      | new_password  | Test123!  |
    Then 系统应验证旧密码
    And 验证新密码强度
    And 更新用户密码
    And 返回成功响应

  Scenario: 修改密码失败 - 旧密码错误
    When 用户使用错误的旧密码尝试修改密码:
      | Field         | Value     |
      | old_password  | wrongpass |
      | new_password  | Test123!  |
    Then 系统应返回400错误
    And 错误信息应说明旧密码验证失败

  Scenario: 修改密码失败 - 新密码强度不足
    When 用户尝试设置弱密码:
      | Field         | Value   |
      | old_password  | oldpass |
      | new_password  | 123456  |
    Then 系统应返回400错误
    And 错误信息应说明密码强度不足