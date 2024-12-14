Feature: 用户注册
  作为潜在用户
  我想创建新账户
  以便使用系统功能

  Background: 
    Given 系统处于可注册状态

  Scenario: 成功注册新用户
    When 用户提供以下注册信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
      | email    | test@example.com  |
    Then 系统应创建新用户账户
    And 返回成功响应
    And 自动登录用户

  Scenario: 管理员分配用户并固定密码
    Given 当前用户具有管理员权限
    When 管理员提供以下注册信息:
      | Field    | Value             |
      | username | newuser           |
      | password | FixedPass123!     |
      | email    | newuser@example.com |
    Then 系统应创建新用户账户
    And 返回成功响应

  Scenario: 管理员分配用户并通过邮件发送注册后的密码
    Given 当前用户具有管理员权限
    When 管理员提供以下注册信息:
      | Field    | Value             |
      | username | newuser           |
      | email    | newuser@example.com |
    Then 系统应创建新用户账户
    And 系统应生成随机密码并通过邮件发送给用户
    And 返回成功响应

  Scenario: 管理员分配用户并通过手机号码发送注册后的密码
    Given 当前用户具有管理员权限
    When 管理员提供以下注册信息:
      | Field    | Value             |
      | username | newuser           |
      | phone    | 13800138000       |
    Then 系统应创建新用户账户
    And 系统应生成随机密码并通过手机号码发送给用户
    And 返回成功响应

  Scenario: 用户注册时要求邮件验证
    When 用户提供以下注册信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
      | email    | test@example.com  |
    Then 系统应发送验证邮件到用户邮箱
    And 用户点击验证链接后系统应创建新用户账户
    And 返回成功响应

  Scenario: 用户注册时要求手机号码验证
    When 用户提供以下注册信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
      | phone    | 13800138000       |
    Then 系统应发送验证短信到用户手机
    And 用户输入短信验证码后系统应创建新用户账户
    And 返回成功响应
