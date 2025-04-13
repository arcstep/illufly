# Illufly API 架构说明

Illufly API是一个基于FastAPI构建的后端API服务，支持用户认证、文件管理、聊天对话、记忆管理、TTS等功能。经过重构优化，API服务采用了模块化的设计方式，便于扩展和维护。

## 架构概述

API服务采用模块化设计，各个功能模块独立实现并按特定顺序挂载。主要组成部分：

1. **核心应用** - 由`create_app`函数创建的FastAPI应用
2. **服务模块** - 各种功能服务的实现
3. **API端点** - 各模块的HTTP接口
4. **通用组件** - 如认证中间件、代理中间件等
5. **静态资源** - 服务静态文件的组件

## 模块挂载顺序

服务按以下顺序挂载，确保依赖关系正确：

1. 用户认证 API
2. API密钥管理 API
3. 聊天对话 API
4. 记忆管理 API
5. 文件管理 API
6. TTS代理服务
7. 其他代理服务
8. 静态文件服务

## 关键特性

### 1. 用户认证

使用soulseal库实现的令牌认证系统，支持：

- JWT令牌认证
- 令牌自动续订
- 用户角色和权限控制

```python
# 使用token_sdk进行用户验证
require_user = token_sdk.get_auth_dependency(logger=logger)

@app.get("/protected-endpoint")
async def protected_endpoint(token_claims: Dict[str, Any] = Depends(require_user)):
    user_id = token_claims['user_id']
    # 处理受保护的资源
```

### 2. 通用代理中间件

用于转发请求到后端服务，简化微服务通信：

```python
# 配置多个代理服务
proxy_services = {
    "/api/tts": "http://tts-service:8000",    # TTS服务
    "/api/vector": "http://vector-service:8080",  # 向量搜索服务 
    "/api/ocr": "http://ocr-service:7070"     # OCR文字识别服务
}

# 挂载所有代理服务
mount_proxy_services(app, proxy_services)
```

### 3. 统一的路由挂载方式

使用通用的路由挂载函数，简化API注册：

```python
# 挂载路由
mount_routes(app, handlers, "Illufly Backend - My Module")
```

### 4. 文件管理服务

升级后的文件管理服务支持：

- 文件上传与下载
- 流式文件传输
- 元数据管理
- 文件处理（转换、切片等）
- 存储空间管理

```python
# 初始化文件服务
files_service = FilesService(
    base_dir="./storage/files",
    max_file_size=50 * 1024 * 1024,  # 50MB
    max_total_size_per_user=200 * 1024 * 1024  # 200MB
)
```

## 如何扩展

### 添加新的API模块

1. 在`api`目录下创建新的模块目录
2. 实现模块的服务类和端点函数
3. 在`start.py`中添加对应的挂载函数
4. 在`create_app`中调用挂载函数

示例：
```python
# 1. 创建模块端点
def create_my_module_endpoints(app, token_sdk, ...):
    # 实现端点
    return handlers

# 2. 创建挂载函数
def mount_my_module_api(app, prefix, token_sdk, ...):
    """挂载我的模块API"""
    logger.info("正在挂载我的模块API...")
    
    handlers = create_my_module_endpoints(app, token_sdk, ...)
    mount_routes(app, handlers, "Illufly Backend - My Module")

# 3. 在create_app中调用
mount_my_module_api(app, prefix, token_sdk, ...)
```

### 添加代理服务

只需在应用创建时配置代理服务映射：

```python
app = await create_app(
    proxy_services={
        "/api/service1": "http://service1:8000",
        "/api/service2": "http://service2:9000"
    }
)
```

## 配置选项

应用创建支持以下配置选项：

```python
app = await create_app(
    db_path="./db",              # 数据库路径
    prefix="/api",               # API路径前缀
    base_url="https://api.example.com",  # API基础URL（用于生成链接）
    static_dir="./static",       # 静态文件目录
    files_dir="./files",         # 文件存储目录
    cors_origins=["http://localhost:3000"],  # CORS来源
    proxy_services={...},        # 代理服务配置
)
```

## 环境变量

常用环境变量：

- `TTS_HOST` 和 `TTS_PORT` - TTS服务配置
- `ILLUFLY_VALID_MODELS` - 可用的聊天模型列表

## 依赖关系

- FastAPI - Web框架
- soulseal - 认证库
- voidring - 数据存储
- httpx - HTTP客户端（用于代理） 