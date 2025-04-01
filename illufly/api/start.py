from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pathlib import Path
from typing import Optional, List, Set

import logging

from ..__version__ import __version__
from ..rocksdb import IndexedRocksDB
from ..llm import ChatAgent
from ..llm import ThreadManager
from .auth import TokensManager, UsersManager, create_auth_endpoints
from .api_keys import ApiKeysManager, create_api_keys_endpoints
from .openai import create_openai_endpoints
from .chat import create_chat_endpoints
from .static_files import StaticFilesManager

logger = logging.getLogger("illufly")

def setup_logging(log_level: int = logging.INFO):
    """配置全局日志"""
    # 配置根记录器
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()],
        force=True
    )

def setup_spa_middleware(app: FastAPI, static_dir: Path, exclude_paths: List[str] = []):
    """设置 SPA 中间件，处理客户端路由"""
    logger = logging.getLogger("illufly")
    
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
    log_level: int = logging.INFO
) -> FastAPI:
    """创建 FastAPI 应用"""

    setup_logging(log_level)

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
    db_path.parent.mkdir(parents=True, exist_ok=True)
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

    # 初始化管理器实例
    tokens_manager = TokensManager(db)
    users_manager = UsersManager(db)
    api_keys_manager = ApiKeysManager(db)

    mount_auth_api(app, prefix, tokens_manager, users_manager)
    mount_api_keys_api(app, prefix, base_url, tokens_manager, api_keys_manager)
    mount_agent_api(app, prefix, agent, thread_manager, tokens_manager)
    
    static_manager = mount_static_files(app, prefix, static_dir)

    @app.on_event("shutdown")
    async def cleanup():
        """
        应用关闭时清理资源
        """
        if static_manager:
            static_manager.cleanup()
        
        logger.warning(f"Illufly API 关闭完成")

    logger.info(f"Illufly API 启动完成: {prefix}/docs")
    return app

def mount_auth_api(app: FastAPI, prefix: str, tokens_manager: TokensManager, users_manager: UsersManager):
    # 用户管理和认证路由
    auth_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        users_manager=users_manager,
        prefix=prefix
    )
    for (method, path, handler) in auth_handlers:
        app.add_api_route(
            path=path,
            endpoint=handler,
            methods=[method],
            response_model=getattr(handler, "__annotations__", {}).get("return"),
            summary=getattr(handler, "__doc__", "").split("\n")[0] if handler.__doc__ else None,
            description=getattr(handler, "__doc__", None),
            tags=["Illufly Backend - Auth"])

def mount_api_keys_api(app: FastAPI, prefix: str, base_url: str, tokens_manager: TokensManager, api_keys_manager: ApiKeysManager):
    # APIKEY 路由
    api_keys_handlers = create_api_keys_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        api_keys_manager=api_keys_manager,
        prefix=prefix,
        base_url=base_url
    )
    for (method, path, handler) in api_keys_handlers:
        app.add_api_route(
            path=path,
            endpoint=handler,
            methods=[method],
            response_model=getattr(handler, "__annotations__", {}).get("return"),
            summary=getattr(handler, "__doc__", "").split("\n")[0] if handler.__doc__ else None,
            description=getattr(handler, "__doc__", None),
            tags=["Illufly Backend - API Keys"])

def mount_static_files(app: FastAPI, prefix: str, static_dir: Optional[str]):
    # 加载静态资源环境
    static_manager = None
    if Path(__file__).parent.joinpath("static").exists() and static_dir is None:
        static_path = Path(__file__).parent.joinpath("static")
    else:
        static_manager = StaticFilesManager(static_dir=static_dir)
        static_path = static_manager.setup()

    if static_path:
        # 设置 SPA 中间件
        setup_spa_middleware(app, static_path, exclude_paths=[f"{prefix}/", "/docs", "/openapi.json"])
        
        # 挂载静态文件（作为后备）
        app.mount("/", StaticFiles(
            directory=str(static_path), 
            html=True
        ), name="static")
    
    return static_manager

def mount_agent_api(app: FastAPI, prefix: str, agent: ChatAgent, thread_manager: ThreadManager, tokens_manager: TokensManager):
    # Chat 路由
    chat_handlers = create_chat_endpoints(
        app=app,
        agent=agent,
        thread_manager=thread_manager,
        tokens_manager=tokens_manager,
        prefix=prefix
    )
    for (method, path, handler) in chat_handlers:
        app.add_api_route(
            path=path,
            endpoint=handler,
            methods=[method],
            response_model=getattr(handler, "__annotations__", {}).get("return"),
            summary=getattr(handler, "__doc__", "").split("\n")[0] if handler.__doc__ else None,
            description=getattr(handler, "__doc__", None),
            tags=["Illufly Backend - Chat"])
