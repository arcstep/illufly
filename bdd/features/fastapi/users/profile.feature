# profile_management.feature
Feature: 个人信息管理
  作为系统用户
  我想管理我的个人信息
  以保持信息的准确性

  Scenario: 查看个人信息
    When 用户请求获取个人信息
    Then 系统应返回用户详细信息，包含:
      | Field                  | Type    |
      | user_id               | string  |
      | username              | string  |
      | email                 | string  |
      | roles                 | array   |
      | is_active            | boolean |
      | is_locked            | boolean |
      | require_password_change | boolean |

  Scenario: 更新个人信息
    When 用户更新个人信息:
      | Field       | Value          |
      | nickname    | 测试用户        |
      | avatar      | new_avatar.jpg |
      | phone       | 13800138000    |
    Then 系统应保存更新的信息
    And 返回成功响应

  Scenario: 更新用户设置
    When 用户更新个人设置:
      | Field     | Value    |
      | language  | zh_CN    |
      | theme     | dark     |
      | timezone  | Asia/Shanghai |
    Then 系统应保存新的设置
    And 返回成功响应