# 文档元信息
@auth @login @api-doc
Feature: 用户多设备登录管理
  """
  用户认证系统 - 多设备登录管理
  基础路径: /api/auth
  版本: 0.7
  最后更新: 2024-12-15
  负责人: @xuehongwei

  ## API 端点
  - POST /auth/login: 用户登录
    - 参数 (Form):
      - username: str, 必填, 用户名
      - password: str, 必填, 密码
    - 返回:
      - success: bool
      - user_info: dict
      - require_password_change: bool
    - 错误码:
      - 400: 参数验证失败
      - 401: 认证失败
      - 403: 账户锁定/未激活
      - 500: 服务器错误

  - POST /auth/logout: 退出登录
    - 参数: 无
    - 返回:
      - success: bool
      - message: str
    - Cookie:
      - 清除 access_token
      - 清除 refresh_token

  - POST /auth/change-password: 修改密码
    - 参数 (Form):
      - current_password: str, 必填
      - new_password: str, 必填
    - 返回:
      - success: bool
      - message: str
    - 错误码:
      - 400: 密码验证失败
      - 500: 服务器错误

  # 功能概述
  实现支持多设备同时登录的用户认证系统，确保安全性的同时提供便捷的用户体验。

  ## 业务背景
  - 用户需要在多个设备（手机、平板、电脑等）上同时使用系统
  - 需要支持单个设备的独立退出
  - 需要支持零登录(Zero Login)以提升用户体验

  ## 关键术语
  - 零登录：利用刷新令牌自动完成登录，无需用户输入凭据
  - 设备令牌：每个设备独立的认证标识
  - HTTP-only Cookie：仅服务器可访问的安全Cookie

  ## 安全考虑
  - 所有密码必须符合强度要求
  - 支持账户锁定机制
  - 使用 HTTP-only Cookie 存储认证信息

  ## 相关需求
  - REQ-001: 多设备支持
  - REQ-002: 设备管理
  - SEC-001: 认证安全策略
  """

  Background: 测试环境准备
    Given FastAPI 已经准备好
    And 清理测试数据
    And 系统已有注册用户:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
      | email    | test1@example.com |
      | roles    | ["user"]         |
    And 系统已有注册用户:
      | 字段    | 值             |
      | username | testuser2         |
      | password | Test123!@#        |
      | email    | test2@example.com |
      | roles    | ["user"]         |
    And 系统已有注册用户:
      | 字段    | 值             |
      | username | admin             |
      | password | Test123!@#        |
      | email    | admin@example.com |
      | roles    | ["admin", "user"] |

  # 以下是核心场景
  @core @happy-path
  Scenario: 成功登录单个设备
    """
    最基本的登录场景，验证用户凭据并建立会话。
    
    注意事项：
    - 密码必须符合强度要求
    - 登录成功后需要设置安全的 Cookie
    - 需要检查是否需要强制修改密码
    """
    When 用户登录到设备:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
    Then 用户凭据应验证成功
    And 返回成功响应，包含:
      | 字段                 | 类型    |
      | success              | boolean |
      | user_info            | object  |
      | require_password_change | boolean |
    And HTTP响应存在认证令牌

  @core
  Scenario: 成功在多个设备上登录
    When 用户登录到设备:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
      | device_id | device_a         |
    And 用户登录到设备:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
      | device_id | device_b         |
    Then 用户凭据应验证成功
    And 返回成功响应，包含:
      | 字段                 | 类型    |
      | success              | boolean |
      | user_info            | object  |
      | require_password_change | boolean |
    And HTTP响应存在认证令牌
    And 服务端应存在用户的令牌:
      | 字段    | 值          |
      | username | testuser1 |
      | device_id | device_a |
      | device_id | device_b |

  @core
  Scenario: 单个设备退出
    When 用户登录到设备:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
      | device_id | device_a         |
    And 用户登录到设备:
      | 字段    | 值             |
      | username | testuser1         |
      | password | Test123!@#        |
      | device_id | device_b         |
    And 系统验证用户凭据
    And 用户在最近使用的设备上退出登录
    Then 服务端应存在用户的令牌:
      | 字段    | 值          |
      | username | testuser1 |
      | device_id | device_a |
    And 服务端不应存在用户的令牌:
      | 字段    | 值          |
      | username | testuser1 |
      | device_id | device_b |

  @error
  Scenario: 登录失败 - 错误的凭据
    When 用户使用错误的凭据登录:
      | 字段    | 值             |
      | username | testuser          |
      | password | wrongpassword     |
    Then 系统应返回401未授权错误
    And 错误信息应包含认证失败的详情


  """
  ## 实现注意事项

  ### 安全实现
  - 密码验证必须使用恒定时间比较，防止计时攻击
  - 所有登录尝试需要记录审计日志
  - 实现 rate limiting 防止暴力破解
  - 考虑使用 IP 信誉系统
  
  ### 会话管理
  - 使用 Redis 存储会话状态
  - 实现会话集群同步机制
  - 设置合理的会话超时时间
  - 维护设备令牌映射关系

  ### 性能考虑
  - 密码哈希使用适当的计算强度
  - 令牌验证需要缓存机制
  - 考虑登录请求的并发处理
  - 实现登录队列防止峰值冲击

  ### 监控告警
  - 监控异常登录行为
  - 设置账户锁定告警
  - 记录地理位置异常
  - 可疑IP活动检测

  ### 运维支持
  - 提供管理员解锁接口
  - 支持会话强制失效
  - 实现登录日志查询
  - 提供会话状态诊断

  ### 客户端集成
  - 提供登录状态检查接口
  - 实现令牌自动刷新机制
  - 处理多标签页同步
  - 支持优雅的掉线重连
  """
