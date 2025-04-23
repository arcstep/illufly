from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
import httpx
import logging
from typing import Dict, Optional, List, Any, Callable
import time
import re
import json

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

def create_proxy_handler(target_url: str, path_template: str = "", timeout: float = 300.0):
    """创建代理处理函数"""
    async def proxy_handler(request: Request):
        """代理请求到后端服务"""
        # 路径处理
        target_path = path_template
        
        if '{' in path_template:
            template_parts = path_template.split('/')
            request_parts = request.url.path.split('/')
            
            param_values = {}
            for i, part in enumerate(template_parts):
                if '{' in part and '}' in part:
                    param_name = part.strip('{}')
                    offset = len(request_parts) - len(template_parts)
                    if i + offset >= 0 and i + offset < len(request_parts):
                        param_values[param_name] = request_parts[i + offset]
            
            for param_name, param_value in param_values.items():
                target_path = target_path.replace(f"{{{param_name}}}", param_value)
        
        service_url = f"{target_url}/{target_path.lstrip('/')}" if target_path else target_url
        logger.info(f"代理请求: {request.method} {request.url.path} -> {service_url}")
        
        # 检查是否为SSE请求
        is_event_stream = "text/event-stream" in request.headers.get("accept", "")
        if is_event_stream:
            logger.info(f"检测到SSE请求: {service_url}")
        
        client_timeout = httpx.Timeout(
            connect=10.0,
            read=None if is_event_stream else timeout,
            write=60.0,
            pool=5.0
        )
        
        async with httpx.AsyncClient(timeout=client_timeout) as client:
            try:
                # 准备标准HTTP请求参数
                headers = {k: v for k, v in request.headers.items() 
                          if k.lower() not in ["host", "content-length"]}
                
                # 处理认证
                auth_token = request.cookies.get("access_token")
                if auth_token and "authorization" not in [k.lower() for k in headers]:
                    headers["Authorization"] = f"Bearer {auth_token}"
                
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
                
                # 发送请求
                response = await client.request(**request_kwargs)
                
                # 记录响应信息
                logger.info(f"收到后端响应: {service_url}, 状态码: {response.status_code}, " 
                           f"内容类型: {response.headers.get('content-type', '未知')}")
                
                # 如果是SSE响应，添加特殊处理
                if is_event_stream or "text/event-stream" in response.headers.get("content-type", ""):
                    logger.info(f"开始处理SSE响应: {service_url}")
                    
                    # 创建一个包装的生成器来记录SSE事件
                    async def log_sse_events():
                        event_count = 0
                        buffer = b""
                        event_type = ""
                        event_data = ""
                        
                        # SSE事件解析正则
                        event_pattern = re.compile(b"event: (.*?)(?:\r\n|\n)")
                        data_pattern = re.compile(b"data: (.*?)(?:\r\n|\n)")
                        
                        try:
                            async for chunk in response.aiter_bytes():
                                # 增加到缓冲区
                                buffer += chunk
                                
                                # 查找完整的事件 (以空行分隔)
                                events = buffer.split(b"\n\n")
                                
                                # 最后一个可能不完整，保留到下一次
                                if not buffer.endswith(b"\n\n"):
                                    buffer = events.pop()
                                else:
                                    buffer = b""
                                    
                                # 处理完整的事件
                                for event_chunk in events:
                                    if not event_chunk.strip():
                                        continue
                                        
                                    event_count += 1
                                    
                                    # 提取事件类型和数据
                                    event_match = event_pattern.search(event_chunk)
                                    event_type = event_match.group(1).decode("utf-8") if event_match else "message"
                                    
                                    data_match = data_pattern.search(event_chunk)
                                    if data_match:
                                        event_data = data_match.group(1).decode("utf-8")
                                        try:
                                            # 尝试解析JSON数据以便更好地记录
                                            event_json = json.loads(event_data)
                                            logger.info(f"SSE事件 #{event_count}: 类型={event_type}, 数据={json.dumps(event_json, ensure_ascii=False)}")
                                        except:
                                            # 非JSON数据
                                            logger.info(f"SSE事件 #{event_count}: 类型={event_type}, 数据={event_data}")
                                    else:
                                        logger.info(f"SSE事件 #{event_count}: 类型={event_type}, 无数据")
                                
                                # 将原始块传给客户端
                                yield chunk
                            
                            logger.info(f"SSE响应完成: {service_url}, 总事件数: {event_count}")
                            
                            # 处理最后可能的不完整事件
                            if buffer:
                                logger.info(f"剩余未完成事件缓冲区: {buffer}")
                                
                        except Exception as e:
                            logger.error(f"SSE传输出错: {service_url}, {str(e)}")
                            raise
                    
                    return StreamingResponse(
                        content=log_sse_events(),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.headers.get("content-type", "application/json")
                    )
                else:
                    # 非SSE响应
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