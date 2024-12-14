Feature: 用户多设备登录管理
  作为注册用户
  我想在多个设备上登录系统
  以便访问受保护的功能，并在需要时退出单个设备

  Background:
    Given 系统已有注册用户

  Scenario: 成功登录单个设备
    When 用户在设备A提供正确的登录信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
    Then 系统应验证用户凭据
    And 返回成功响应，包含:
      | Field                 | Type    |
      | success              | boolean |
      | token_data          | object  |
      | require_password_change | boolean |
    And 设置设备A的认证Cookie

  Scenario: 成功在多个设备上登录
    Given 用户已在设备A登录
    When 用户在设备B提供正确的登录信息:
      | Field    | Value             |
      | username | testuser          |
      | password | Test123!@#        |
    Then 系统应验证用户凭据
    And 返回成功响应，包含:
      | Field                 | Type    |
      | success              | boolean |
      | token_data          | object  |
      | require_password_change | boolean |
    And 设置设备B的认证Cookie

  Scenario: 单个设备退出
    Given 用户已在设备A和设备B登录
    When 用户在设备A请求退出
    Then 系统应清除设备A的认证Cookie
    And 设备B的令牌仍然有效

  Scenario: 零登录支持
    Given 用户持有有效的http_only刷新令牌
    When 用户请求零登录
    Then 系统应验证刷新令牌
    And 返回成功响应，包含新的访问令牌

  Scenario: 登录失败 - 错误的凭据
    When 用户在设备A提供错误的登录信息:
      | Field    | Value             |
      | username | testuser          |
      | password | wrongpassword     |
    Then 系统应返回401未授权错误
    And 错误信息应包含认证失败的详情

  Scenario: 登录失败 - 账户被锁定
    Given 用户账户已被锁定
    When 用户在设备A尝试登录
    Then 系统应返回403禁止访问错误
    And 错误信息应说明账户已锁定

  Scenario: 登录失败 - 账户未激活
    Given 用户账户未激活
    When 用户在设备A尝试登录
    Then 系统应返回403禁止访问错误
    And 错误信息应说明账户未激活

  Scenario: 登录失败 - 缺少必填字段
    When 用户在设备A提供不完整的登录信息:
      | Field    | Value    |
      | username | testuser |
    Then 系统应返回400错误
    And 错误信息应说明缺少必填字段
