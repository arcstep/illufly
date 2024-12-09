# Auth Module Documentation

## Overview
认证模块提供用户认证、注册和会话管理的功能。包括：
- 用户注册与邮箱验证
- 登录/登出管理
- JWT token 管理
- 密码重置流程

## API Endpoints

### 用户注册与验证
```
POST /api/auth/register
- 用户注册
- Request Body: {username, password, email, invite_code?}
- Response: {username, email, created_at, last_login}

POST /api/auth/verify-email
- 验证邮箱
- Query Params: token
- Response: {message}

POST /api/auth/resend-verification
- 重发验证邮件
- Requires: Authentication
- Response: {message}
```

### 认证管理
```
POST /api/auth/login
- 用户登录
- Form Data: {username, password}
- Response: {username, ...user_info}

POST /api/auth/logout
- 用户登出
- Requires: Authentication
- Response: {message}

POST /api/auth/refresh-token
- 刷新访问令牌
- Requires: Valid refresh token in cookies
- Response: {message}
```

### 密码管理
```
POST /api/auth/password/reset-request
- 请求重置密码
- Request Body: {email}
- Response: {message}

POST /api/auth/password/reset
- 重置密码
- Request Body: {reset_token, new_password}
- Response: {message}

POST /api/auth/password/change
- 修改密码
- Requires: Authentication
- Request Body: {old_password, new_password}
- Response: {message}
```

## 使用示例

### 用户注册
```python
from fastapi import FastAPI
from illufly.fastapi.auth import create_auth_endpoints
from illufly.fastapi.user.manager import UserManager

app = FastAPI()
user_manager = UserManager()

# 创建认证端点
create_auth_endpoints(app, user_manager)
```

### 自定义认证函数
```python
def custom_auth_func(username: str, password: str):
    # 自定义认证逻辑
    user = user_manager.authenticate(username, password)
    if user:
        return {"username": username, "role": user.role}
    return None

create_auth_endpoints(app, user_manager, auth_func=custom_auth_func)
```

## 模块结构
```
auth/
├── __init__.py          # 模块入口点
├── endpoints.py         # API 端点定义
├── dependencies.py      # 依赖函数（如 get_current_user）
├── models.py           # 数据模型定义
├── utils.py            # 工具函数
└── README.md           # 模块文档
```