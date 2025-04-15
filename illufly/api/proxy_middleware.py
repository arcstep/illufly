from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import logging
from typing import Dict, Optional, List, Any, Callable

logger = logging.getLogger("illufly.proxy")

def normalize_url(url: str) -> str:
    """规范化URL，确保不会有重复的协议前缀"""
    url = url.strip()
    
    if "://" in url:
        parts = url.split("://")
        if len(parts) > 2:
            return f"{parts[-2]}://{parts[-1]}"
        return url
    else:
        return f"http://{url}"

def create_proxy_handler(target_url: str, path_template: str = "", timeout: float = 30.0):
    """创建代理处理函数
    
    Args:
        target_url: 目标服务的URL
        path_template: 原始路径模板，可能包含{param}占位符
        timeout: 请求超时时间
    """
    async def proxy_handler(request: Request):
        """代理请求到后端服务"""
        # 获取原始请求路径
        request_path = request.url.path
        
        # 从原始路径模板中提取目标路径
        # 首先保留目标服务的路径部分
        target_path = path_template
        
        # 对于包含路径参数的URL（如 /oculith/files/{file_id}）
        if '{' in path_template:
            # 解析请求URL，正确提取文件ID
            # 例如 /api/oculith/files/123456 -> /oculith/files/123456
            
            # 从请求中提取实际ID
            path_parts = request_path.split('/')
            
            # 查找最后一个部分，它通常是ID
            actual_id = path_parts[-1]  # 例如 "123456.pdf"
            
            # 简单替换路径模板中的参数部分
            target_path = path_template.replace("{file_id}", actual_id)
        
        # 构建最终服务URL
        service_url = f"{target_url}/{target_path.lstrip('/')}" if target_path else target_url
        logger.info(f"代理请求: {request.method} {request.url.path} -> {service_url}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # 准备请求参数
                headers = {k: v for k, v in request.headers.items() 
                          if k.lower() not in ["host", "content-length"]}
                
                # 处理认证
                auth_token = request.cookies.get("access_token")
                if auth_token and "authorization" not in [k.lower() for k in headers]:
                    headers["Authorization"] = f"Bearer {auth_token}"
                
                # 基础请求配置
                request_kwargs = {
                    "method": request.method,
                    "url": service_url,
                    "params": dict(request.query_params),
                    "headers": headers,
                    "cookies": request.cookies
                }
                
                # 处理请求体
                content_type = request.headers.get("content-type", "")
                if "application/x-www-form-urlencoded" in content_type:
                    request_kwargs["data"] = dict(await request.form())
                elif "multipart/form-data" in content_type:
                    form = await request.form()
                    files = []
                    data = {}
                    
                    for key, value in form.items():
                        if hasattr(value, "filename") and value.filename:
                            files.append((key, (value.filename, await value.read(), value.content_type)))
                        else:
                            data[key] = value
                    
                    if files: request_kwargs["files"] = files
                    if data: request_kwargs["data"] = data
                else:
                    body = await request.body()
                    if body: request_kwargs["content"] = body
                
                # 发送请求并返回响应
                response = await client.request(**request_kwargs)
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type", "application/json")
                )
            except Exception as e:
                logger.error(f"代理请求错误: {service_url}, {str(e)}")
                return JSONResponse(status_code=503, content={"error": str(e)})
    
    return proxy_handler

def mount_service_proxy(
    app: FastAPI, 
    prefix: str, 
    host: str, 
    port: int,
    service_name: str, 
    tag: str = None,
    env_host: str = None,
    env_port: str = None,
    get_env_fn: Callable = None
) -> bool:
    """挂载服务代理 - 主入口函数"""
    tag = tag or service_name.upper()
    
    # 从环境变量获取配置
    if get_env_fn:
        if env_host and not host:
            host = get_env_fn(env_host, "localhost")
        if env_port and not port:
            port_str = get_env_fn(env_port)
            if port_str:
                try:
                    port = int(port_str)
                except ValueError:
                    logger.warning(f"{env_port}值无效: {port_str}")
    
    # 验证配置
    if not (host and port):
        logger.warning(f"未找到{tag}服务配置，{tag}功能不可用")
        return False
    
    # 构建服务URL
    host = normalize_url(host)
    if "://" in host:
        service_url = f"{host.rstrip('/')}:{port}"
    else:
        service_url = f"http://{host}:{port}"
    
    logger.info(f"配置{tag}服务: {service_url}")
    
    # 获取OpenAPI规范
    try:
        openapi_url = f"{service_url}/openapi.json"
        response = httpx.get(openapi_url, timeout=5.0)
        
        if response.status_code != 200:
            logger.warning(f"无法获取{tag}的OpenAPI规范，状态码: {response.status_code}")
            return False
        
        openapi_spec = response.json()
        routes_added = 0
        paths_total = len(openapi_spec.get("paths", {}))
        
        # 提取服务路由前缀
        service_prefix = f"/{service_name}"
        
        # 挂载路由
        for path, path_item in openapi_spec.get("paths", {}).items():
            # 过滤服务路径
            if service_prefix and not path.startswith(service_prefix):
                continue
            
            # 创建路由路径
            api_path = f"{prefix}{path}"
            
            # 为每个HTTP方法创建路由
            for method, operation in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "options", "head", "patch"]:
                    continue
                
                # 获取操作信息
                summary = operation.get("summary", "")
                description = operation.get("description", "")
                
                # 创建代理处理函数
                proxy_fn = create_proxy_handler(
                    target_url=service_url,
                    path_template=path  # 传递原始路径模板
                )
                
                # 设置函数文档和名称
                proxy_fn.__doc__ = description
                
                # 注册路由
                app.add_api_route(
                    path=api_path,
                    endpoint=proxy_fn,
                    methods=[method.upper()],
                    summary=summary,
                    description=description,
                    tags=[f"[PROXY]-{tag}"]
                )
                
                routes_added += 1
                logger.debug(f"已添加路由: {method.upper()} {api_path} -> {service_url}{path}")
        
        logger.info(f"成功挂载{tag}服务: 添加了{routes_added}/{paths_total}个路由")
        return routes_added > 0
    
    except Exception as e:
        logger.error(f"挂载{tag}服务失败: {str(e)}")
        return False 