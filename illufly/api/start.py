from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse

from pathlib import Path
from typing import Optional, List, Set, Dict, Any, Callable, Tuple, Union

from voidring import IndexedRocksDB
from soulseal import (
    create_auth_endpoints,
    UsersManager, User,
    TokensManager, TokenBlacklist, TokenSDK
)

import logging
import httpx
import asyncio

from ..__version__ import __version__
from ..envir import get_env, setup_logging
from ..llm import ChatAgent
from ..llm import ThreadManager
from .models import HttpMethod
from .chat import create_chat_endpoints
from .static_files import StaticFilesManager
from .memory import create_memory_endpoints
from .docs import FilesService, create_docs_endpoints
from .proxy_middleware import mount_service_proxy

setup_logging()
logger = logging.getLogger("illufly")

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
    db_path: str = "./db",
    openai_imitator: str = None,
    provider: str = None,
    title: str = "Illufly API",
    description: str = "Illufly 后端 API 服务",
    prefix: str = "/api",
    base_url: str = "/api",
    static_dir: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    files_dir: Optional[str] = None,
    proxy_services: Optional[Dict[str, str]] = None,
    tts_host: Optional[str] = None,
    tts_port: Optional[int] = None,
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
        expose_headers=["Set-Cookie"]  # 暴露 Set-Cookie 头
    )

    # 初始化数据库
    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)  # 创建db目录本身，而不仅是父目录
    db = IndexedRocksDB(str(db_path))

    # 初始化 ThreadManager
    thread_manager = ThreadManager(db)

    # 初始化 Agent
    agent = ChatAgent(
        db=db,
        provider=provider,
        imitator=openai_imitator
    )

    @app.on_event("startup")
    async def startup():
        """
        应用启动时初始化资源
        """
        await agent.memory.init_retriever()

    #=============================
    # 初始化各种服务实例
    #=============================
    
    # 令牌与认证服务
    token_blacklist = TokenBlacklist()
    tokens_manager = TokensManager(db, token_blacklist, token_storage_method="cookie")
    token_sdk = TokenSDK(tokens_manager=tokens_manager, token_storage_method="cookie")
    users_manager = UsersManager(db)
    
    # 文件管理服务
    files_service = FilesService(
        base_dir=files_dir or str(Path(db_path) / "files"),
        max_file_size=50 * 1024 * 1024,  # 50MB
        max_total_size_per_user=200 * 1024 * 1024  # 200MB
    )
    
    #=============================
    # 按顺序挂载所有API路由
    # 注意：静态文件应该最后挂载，以避免覆盖API路由
    #=============================
    
    # 挂载认证API
    mount_auth_api(app, prefix, tokens_manager, token_blacklist, users_manager)
    
    # 挂载聊天API
    mount_chat_api(app, prefix, agent, thread_manager, token_sdk)
    
    # 挂载记忆API
    mount_memory_api(app, prefix, agent, token_sdk)
    
    # 挂载文件管理API
    mount_docs_api(app, prefix, token_sdk, files_service)
    
    # 挂载TTS API
    mount_tts_api(app, prefix, tts_host, tts_port)
    
    # 最后挂载静态文件服务
    static_manager = None
    
    # 处理静态文件
    if static_dir or Path(__file__).parent.joinpath("static").exists():
        static_manager = mount_static_files(app, prefix, static_dir)
    
    @app.on_event("shutdown")
    async def cleanup():
        """应用关闭时清理资源"""
        if static_manager:
            static_manager.cleanup()
        
        logger.warning("Illufly API 关闭完成")

    logger.info(f"Illufly API 启动完成: {prefix}/docs")
    return app

def mount_auth_api(app: FastAPI, prefix: str, tokens_manager: TokensManager, token_blacklist: TokenBlacklist, users_manager: UsersManager):
    """挂载用户认证API"""
    logger.info("正在挂载用户认证API...")
    
    # 用户管理和认证路由
    auth_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        token_blacklist=token_blacklist,
        users_manager=users_manager,
        prefix=prefix
    )
    
    mount_routes(app, auth_handlers, "Illufly Backend - Auth")

def mount_chat_api(app: FastAPI, prefix: str, agent: ChatAgent, thread_manager: ThreadManager, token_sdk: TokenSDK):
    """挂载聊天API"""
    logger.info("正在挂载聊天API...")
    
    # 聊天路由
    chat_handlers = create_chat_endpoints(
        app=app,
        agent=agent,
        thread_manager=thread_manager,
        token_sdk=token_sdk,
        prefix=prefix
    )
    
    mount_routes(app, chat_handlers, "Illufly Backend - Chat")

def mount_memory_api(app: FastAPI, prefix: str, agent: ChatAgent, token_sdk: TokenSDK):
    """挂载记忆API"""
    logger.info("正在挂载记忆API...")
    
    # 记忆路由
    memory_handlers = create_memory_endpoints(
        app=app,
        agent=agent,
        token_sdk=token_sdk,
        prefix=prefix
    )
    
    mount_routes(app, memory_handlers, "Illufly Backend - Memory")


def mount_docs_api(app: FastAPI, prefix: str, token_sdk: TokenSDK, files_service: FilesService):
    """挂载文件管理API"""
    logger.info("正在挂载文件管理API...")
    
    # 文件管理路由（注意：create_files_endpoints已自行挂载路由）
    create_docs_endpoints(
        app=app,
        token_sdk=token_sdk,
        files_service=files_service,
        prefix=prefix
    )

def mount_tts_api(app: FastAPI, prefix: str, tts_host: Optional[str], tts_port: Optional[int]):
    """挂载TTS API"""
    # 整合所有代理服务配置
    tts_url = None
    
    # 尝试从环境变量获取TTS配置
    if not tts_host:
        tts_host = get_env("TTS_HOST", None)
    if not tts_port:
        tts_port_str = get_env("TTS_PORT", None)
        if tts_port_str:
            try:
                tts_port = int(tts_port_str)
            except ValueError:
                logger.warning(f"TTS_PORT值无效: {tts_port_str}")
                tts_port = None
    
    # 添加TTS服务配置
    if tts_host and tts_port:
        tts_url = f"http://{tts_host}:{tts_port}"
        logger.info(f"已配置TTS服务: {tts_url}")
        
        # 挂载TTS服务，使用通用代理方法
        mount_service_proxy(
            app=app,
            service_url=tts_url,
            prefix=prefix,
            service_path="tts",
            tag="TTS"
        )
    else:
        logger.warning("未找到TTS服务配置，TTS功能不可用")
    

def mount_static_files(app: FastAPI, prefix: str, static_dir: Optional[str]):
    """挂载静态文件服务"""
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
