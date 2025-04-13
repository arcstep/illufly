from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import logging
from typing import Dict, Optional, List, Any, Callable, Tuple

logger = logging.getLogger("illufly.proxy")

def create_proxy_handler(target_url: str, path: str = "", timeout: float = 30.0, preserve_prefix: bool = True):
    """创建代理处理函数
    
    Args:
        target_url: 目标服务的URL
        path: 服务上的路径
        timeout: 请求超时时间
        preserve_prefix: 是否保留路径前缀
        
    Returns:
        异步处理函数
    """
    async def proxy_handler(request: Request):
        """代理请求到后端服务"""
        # 如果 preserve_prefix 为 True，则保留完整路径，否则使用参数中的 path
        if preserve_prefix:
            # 提取请求路径的最后部分作为目标路径
            request_path = request.url.path
            route_path = path + request_path.split("/")[-1]
            service_url = f"{target_url}/{route_path}" if route_path else target_url
        else:
            service_url = f"{target_url}/{path}" if path else target_url
            
        logger.info(f"代理请求: {request.method} {request.url.path} -> {service_url}")
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                # 获取请求信息
                method = request.method
                
                # 获取并转发认证信息
                headers = {k: v for k, v in request.headers.items() 
                           if k.lower() not in ["host", "content-length"]}
                
                # 处理Auth头和Cookie
                auth_token = request.cookies.get("access_token")
                if auth_token and "authorization" not in [k.lower() for k in headers]:
                    headers["Authorization"] = f"Bearer {auth_token}"
                
                params = dict(request.query_params)
                
                # 设置请求参数
                request_kwargs = {
                    "method": method,
                    "url": service_url,
                    "params": params,
                    "headers": headers,
                    "cookies": request.cookies
                }
                
                # 处理不同类型的请求体
                content_type = request.headers.get("content-type", "")
                
                if "application/x-www-form-urlencoded" in content_type:
                    # 表单数据
                    form_data = await request.form()
                    request_kwargs["data"] = dict(form_data)
                    logger.debug(f"表单数据: {request_kwargs['data']}")
                elif "multipart/form-data" in content_type:
                    # 多部分表单数据（文件上传）
                    form_data = await request.form()
                    files = []
                    data = {}
                    
                    for key, value in form_data.items():
                        if hasattr(value, "filename") and value.filename:
                            # 文件字段
                            file_content = await value.read()
                            files.append(
                                (key, (value.filename, file_content, value.content_type))
                            )
                        else:
                            # 普通字段
                            data[key] = value
                    
                    if files:
                        request_kwargs["files"] = files
                    if data:
                        request_kwargs["data"] = data
                    logger.debug(f"多部分表单数据: 字段={data}, 文件数={len(files)}")
                else:
                    # JSON或其他类型的请求体
                    body = await request.body()
                    if body:
                        request_kwargs["content"] = body
                
                # 发送请求
                logger.debug(f"发送请求: {method} {service_url}")
                response = await client.request(**request_kwargs)
                logger.debug(f"收到响应: 状态={response.status_code}")
                
                # 返回响应
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.headers.get("content-type", "application/json")
                )
                
            except Exception as e:
                logger.error(f"代理请求错误: {service_url}, {str(e)}")
                return JSONResponse(
                    status_code=503,
                    content={"status": "error", "error": str(e)}
                )
    
    return proxy_handler

def mount_openapi_routes(
    app: FastAPI, 
    service_url: str, 
    prefix: str, 
    tag: str,
    base_path: str = ""
) -> bool:
    """挂载OpenAPI服务路由
    
    从服务的OpenAPI规范自动生成路由。
    
    Args:
        app: FastAPI应用实例
        service_url: 后端服务URL
        prefix: API路径前缀
        tag: API文档标签
        base_path: 服务基础路径，如"/tts"，如果为空则直接使用服务根路径
        
    Returns:
        是否成功挂载路由
    """
    logger.info(f"尝试挂载OpenAPI路由: {service_url} -> {prefix}{base_path}")
    
    # 尝试获取服务的OpenAPI规范
    try:
        import json
        
        # 请求服务的OpenAPI规范
        openapi_url = f"{service_url}/openapi.json"
        logger.info(f"尝试获取OpenAPI规范: {openapi_url}")
        
        # 同步请求获取规范（启动时一次性操作）
        response = httpx.get(openapi_url, timeout=5.0)
        if response.status_code == 200:
            openapi_spec = response.json()
            
            # 读取服务的路径和操作
            routes_added = 0
            for path, path_item in openapi_spec.get("paths", {}).items():
                # 判断路径是否属于当前服务
                if base_path and not path.startswith(base_path):
                    continue
                    
                # 调整路径前缀
                new_path = f"{prefix}{path}"
                
                # 遍历每个HTTP方法
                for method, operation in path_item.items():
                    if method.lower() not in ["get", "post", "put", "delete", "options", "head", "patch"]:
                        continue
                    
                    logger.info(f"创建路由: {method.upper()} {new_path} -> {service_url}{path}")
                    
                    # 创建代理处理函数
                    # 保留完整路径，去掉前导斜杠
                    proxy_fn = create_proxy_handler(
                        service_url,
                        path.lstrip('/'),
                        timeout=30.0,
                        preserve_prefix=False
                    )
                    
                    # 设置处理函数的文档
                    proxy_fn.__doc__ = operation.get("summary", "") + "\n\n" + operation.get("description", "")
                    
                    # 添加到FastAPI路由
                    app.add_api_route(
                        path=new_path,
                        endpoint=proxy_fn,
                        methods=[method.upper()],
                        summary=operation.get("summary"),
                        description=proxy_fn.__doc__,
                        tags=[tag]
                    )
                    
                    routes_added += 1
                    logger.debug(f"已添加代理路由: {method.upper()} {new_path}")
            
            logger.info(f"成功从OpenAPI规范导入 {routes_added} 个路由")
            return routes_added > 0
        else:
            logger.warning(f"无法获取OpenAPI规范，状态码: {response.status_code}")
    except Exception as e:
        logger.warning(f"导入OpenAPI规范失败: {str(e)}")
    
    return False

def mount_service_proxy(
    app: FastAPI,
    service_url: str,
    prefix: str,
    service_path: str,
    tag: str
) -> bool:
    """挂载服务代理
    
    首先尝试使用OpenAPI规范挂载服务，如失败则手动创建基本路由。
    
    Args:
        app: FastAPI应用实例
        service_url: 后端服务URL
        prefix: API路径前缀
        service_path: 服务路径，如"tts"
        tag: API文档标签
        
    Returns:
        是否成功挂载
    """
    # 完整路径前缀
    full_prefix = f"{prefix}/{service_path}"
    logger.info(f"尝试挂载服务代理: {service_url} -> {full_prefix}")
    
    # 尝试从OpenAPI挂载
    routes_added = mount_openapi_routes(
        app=app,
        service_url=service_url,
        prefix=prefix,
        tag=tag,
        base_path=f"/{service_path}"
    )
    
    if routes_added:
        logger.info(f"成功通过OpenAPI挂载服务 {service_path}")
        return True
    else:
        logger.warning(f"无法通过OpenAPI挂载服务 {service_path}，创建基本转发")
        
        # 创建通用转发
        proxy_fn = create_proxy_handler(
            service_url,
            service_path,
            timeout=30.0,
            preserve_prefix=True
        )
        
        # 添加路由
        app.add_api_route(
            path=f"{prefix}/{service_path}{{path:path}}",
            endpoint=proxy_fn,
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
            summary=f"{tag} API",
            description=f"代理到 {service_url}/{service_path}",
            tags=[tag]
        )
        
        logger.info(f"已添加通用代理路由: {full_prefix}{{path:path}}")
        return True 