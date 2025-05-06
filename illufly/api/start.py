from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

from pathlib import Path
from typing import Optional, List, Set, Dict, Any, Callable, Tuple, Union

from voidring import IndexedRocksDB
from voidrail import ClientDealer
from soulseal import mount_auth_api, TokenSDK, UsersManager

import logging
import httpx
import asyncio
import os

from ..__version__ import __version__
from ..envir import get_env

from ..llm import init_litellm
from ..agents import ChatAgent, ThreadManager
from ..documents import DocumentService
from .schemas import HttpMethod
from .static_files import StaticFilesManager
from .proxy_middleware import mount_service_proxy
from .endpoints import (
    create_chat_endpoints,
    create_memory_endpoints,
    create_documents_endpoints,
    create_topics_endpoints
)

def get_logger():
    """获取当前模块logger"""
    return logging.getLogger("illufly")

# 封装通用的路由挂载函数
def mount_routes(
    app: FastAPI, 
    handlers: List[Tuple[HttpMethod, str, Callable]], 
    tag: str
):
    """将路由处理程序挂载到应用
    
    Args:
        app: FastAPI应用实例
        handlers: 处理程序列表，每项为(HTTP方法, 路径, 处理函数)的元组
        tag: API标签，用于文档分类
    """
    logger = get_logger()
    for method, path, handler in handlers:
        app.add_api_route(
            path=path,
            endpoint=handler,
            methods=[method],
            response_model=getattr(handler, "__annotations__", {}).get("return"),
            summary=getattr(handler, "__doc__", "").split("\n")[0] if handler.__doc__ else None,
            description=getattr(handler, "__doc__", None),
            tags=[tag]
        )
    logger.debug(f"已挂载 {len(handlers)} 个 {tag} 路由")

def setup_spa_middleware(app: FastAPI, static_dir: Path, exclude_paths: List[str] = []):
    """设置 SPA 中间件，处理客户端路由"""
    
    # 扫描所有 HTML 文件的路径
    html_routes = set()
    for file in static_dir.rglob("*.html"):
        route = "/" + file.relative_to(static_dir).with_suffix("").as_posix()
        if route == "/index":
            route = "/"
        html_routes.add(route)
    
    logger = get_logger()
    logger.debug(f"发现HTML路由: {html_routes}")
    
    @app.middleware("http")
    async def spa_middleware(request: Request, call_next):
        path = request.url.path
        
        # API 请求直接传递
        if any(path.startswith(exclude_path) for exclude_path in exclude_paths):
            return await call_next(request)
            
        # 检查是否是已知的 HTML 路由
        if path in html_routes:
            html_file = static_dir / f"{path.lstrip('/')}.html"
            if path == "/":
                html_file = static_dir / "index.html"
            logger.debug(f"返回HTML文件: {html_file}")
            return FileResponse(html_file)
            
        # 检查是否是静态文件
        static_file = static_dir / path.lstrip("/")
        if static_file.is_file():
            logger.debug(f"返回静态文件: {static_file}")
            return FileResponse(static_file)
            
        # 未找到对应文件，返回 index.html（客户端路由处理）
        logger.debug(f"路径 {path} 未找到对应文件，返回 index.html")
        return FileResponse(static_dir / "index.html")

async def create_app(
    data_dir: str = "./.data",
    title: str = "Illufly API",
    description: str = "Illufly 后端 API 服务",
    prefix: str = "/api",
    static_dir: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    router_address: Optional[str] = None
) -> FastAPI:
    """创建 FastAPI 应用"""

    # 创建 FastAPI 应用实例
    version = __version__
    app = FastAPI(
        title=title,
        description=description,
        version=version
    )

    # 配置 CORS
    origins = cors_origins or [
        # Next.js 开发服务器默认端口
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # 不再使用 ["*"]
        allow_credentials=True,  # 允许携带凭证
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Authorization", "Set-Cookie"]  # 暴露头，允许前端读取
    )

    # 初始化数据库
    db_path = Path(os.path.join(data_dir, "rocksdb"))
    db_path.mkdir(parents=True, exist_ok=True)  # 创建db目录本身，而不仅是父目录
    db = IndexedRocksDB(str(db_path))

    @app.on_event("startup")
    async def startup():
        """
        应用启动时初始化资源
        """
        # 初始化litellm
        init_litellm(os.path.join(data_dir, "litellm_cache"))

        await agent.memory.init_retriever()

    # 令牌与认证服务
    token_sdk = TokenSDK(db=db)
    users_manager = UsersManager(db)
    
    # 挂载认证API
    mount_auth_api(app, prefix, token_sdk, users_manager)
    
    # 挂载对话和记忆API
    thread_manager = ThreadManager(db)
    agent = ChatAgent(db=db)
    mount_chat_api(app, prefix, agent, thread_manager, token_sdk)
    mount_memory_api(app, prefix, agent, token_sdk)

    # 挂载文件管理API
    voidrail_client = ClientDealer(router_address)
    document_service = DocumentService(
        os.path.join(data_dir, "documents"),
        voidrail_client=voidrail_client,
        logger=get_logger()
    )
    mount_docs_api(app, prefix, token_sdk, document_service)
    mount_topics_api(app, prefix, token_sdk, document_service)

    # 注意：静态文件应该最后挂载，以避免覆盖API路由
    static_manager = None
    
    # 处理静态文件
    if static_dir or Path(__file__).parent.joinpath("static").exists():
        static_manager = mount_static_files(app, prefix, static_dir)
    
    @app.on_event("shutdown")
    async def cleanup():
        """应用关闭时清理资源"""
        if static_manager:
            static_manager.cleanup()
        
        logger = get_logger()
        logger.warning("Illufly API 关闭完成")

    logger = get_logger()
    logger.info(f"Illufly API 启动完成: {prefix}/docs")
    return app


def mount_chat_api(app: FastAPI, prefix: str, agent: ChatAgent, thread_manager: ThreadManager, token_sdk: TokenSDK):
    """挂载聊天API"""
    logger = get_logger()
    logger.info("正在挂载聊天API...")
    
    # 聊天路由
    handlers = create_chat_endpoints(
        app=app,
        agent=agent,
        thread_manager=thread_manager,
        token_sdk=token_sdk,
        prefix=prefix,
        logger=logger
    )
    
    mount_routes(app, handlers, "Illufly Backend - Chat")

def mount_memory_api(app: FastAPI, prefix: str, agent: ChatAgent, token_sdk: TokenSDK):
    """挂载记忆API"""
    logger = get_logger()
    logger.info("正在挂载记忆API...")
    
    # 记忆路由
    handlers = create_memory_endpoints(
        app=app,
        agent=agent,
        token_sdk=token_sdk,
        prefix=prefix,
        logger=logger
    )
    
    mount_routes(app, handlers, "Illufly Backend - Memory")

def mount_docs_api(app: FastAPI, prefix: str, token_sdk: TokenSDK, document_service: DocumentService):
    """挂载文件管理API"""
    logger = get_logger()
    logger.info("正在挂载文件管理API...")
    
    # 文件管理路由（注意：create_files_endpoints已自行挂载路由）
    handlers = create_documents_endpoints(
        app=app,
        token_sdk=token_sdk,
        document_service=document_service,
        prefix=prefix,
        logger=logger
    )
    mount_routes(app, handlers, "Illufly Backend - Documents")

def mount_topics_api(app: FastAPI, prefix: str, token_sdk: TokenSDK, document_service: DocumentService):
    """挂载主题管理API"""
    logger = get_logger()
    logger.info("正在挂载主题管理API...")
    
    handlers = create_topics_endpoints(
        app=app,
        token_sdk=token_sdk,
        document_service=document_service,
        prefix=prefix,
        logger=logger
    )
    mount_routes(app, handlers, "Illufly Backend - Topics")

def mount_static_files(app: FastAPI, prefix: str, static_dir: Optional[str]):
    """挂载静态文件服务"""
    logger = get_logger()
    logger.info("正在挂载静态文件服务...")
    
    # 加载静态资源环境
    static_manager = None
    if Path(__file__).parent.joinpath("static").exists() and static_dir is None:
        static_path = Path(__file__).parent.joinpath("static")
    else:
        static_manager = StaticFilesManager(static_dir=static_dir)
        static_path = static_manager.setup()

    if static_path:
        # 设置 SPA 中间件，但排除API路径
        api_paths = [prefix, f"{prefix}/", "/docs", "/openapi.json"]
        setup_spa_middleware(app, static_path, exclude_paths=api_paths)
        
        # 挂载静态文件（作为后备）
        # 注意：确保静态文件服务不会捕获API请求
        app.mount("/", StaticFiles(
            directory=str(static_path), 
            html=True
        ), name="static")
        
        logger.info(f"静态文件已挂载: {static_path}")
        logger.info(f"API路径已排除: {api_paths}")
    else:
        logger.warning("未挂载静态文件服务（无有效的静态文件目录）")
    
    return static_manager
