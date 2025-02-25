from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pathlib import Path
from typing import Optional, List, Set

import logging
import zmq.asyncio

from ..__version__ import __version__
from ..rocksdb import IndexedRocksDB
from ..mq.service import ServiceRouter, ClientDealer
from ..thread import ThreadManagerDealer
from .auth.tokens import TokensManager
from .auth.users import UsersManager
from .api_keys import ApiKeysManager
from .auth.endpoints import create_auth_endpoints
from .openai.endpoints import create_openai_endpoints
from .chat.endpoints import create_chat_endpoints
from .static_files import StaticFilesManager

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
    router_address: str = "inproc://router-bus",
    title: str = "Illufly API",
    description: str = "Illufly 后端 API 服务",
    prefix: str = "/api",
    static_dir: Optional[str] = None,
    cors_origins: Optional[List[str]] = None,
    log_level: int = logging.INFO
) -> FastAPI:
    """创建 FastAPI 应用
    
    Args:
        db_path: 数据库路径
        title: API 标题
        description: API 描述
        version: API 版本
        prefix: API 路由前缀
    """
    # 首先设置日志
    setup_logging(log_level)
    logger = logging.getLogger("illufly")

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
    logger.info(f"可接受的 CORS 访问源: {origins}")
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
    db = IndexedRocksDB(str(db_path), logger=logger)

    # 初始化 ZMQ 上下文
    zmq_context = zmq.asyncio.Context()
    router = ServiceRouter(router_address, context=zmq_context)
    zmq_client = ClientDealer(router_address, context=zmq_context, logger=logger)
    thread_manager_dealer = ThreadManagerDealer(db, router_address=router_address, context=zmq_context, logger=logger)

    @app.on_event("startup")
    async def startup():
        """
        应用启动时初始化资源
        """
        await router.start()
        await thread_manager_dealer.start()
        await zmq_client.connect()

    # 初始化管理器实例
    tokens_manager = TokensManager(db, logger=logger)
    users_manager = UsersManager(db, logger=logger)
    api_keys_manager = ApiKeysManager(db, logger=logger)

    # 用户管理和认证路由
    auth_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        users_manager=users_manager,
        prefix=prefix,
        logger=logger
    )
    for (method, path, handler) in auth_handlers:
        getattr(app, method)(path)(handler)

    # OpenAI 路由
    openai_handlers = create_openai_endpoints(
        app=app,
        api_keys_manager=api_keys_manager,
        prefix=prefix,
        logger=logger
    )
    for (method, path, handler) in openai_handlers:
        getattr(app, method)(path)(handler)
    
    # Chat 路由
    chat_handlers = create_chat_endpoints(
        app=app,
        zmq_client=zmq_client,
        tokens_manager=tokens_manager,
        logger=logger
    )
    for (method, path, handler) in chat_handlers:
        getattr(app, method)(path)(handler)

    # 加载静态资源环境
    static_manager = None
    if Path(__file__).parent.joinpath("static").exists() and static_dir is None:
        static_path = Path(__file__).parent.joinpath("static")
    else:
        static_manager = StaticFilesManager(static_dir=static_dir, logger=logger)
        static_path = static_manager.setup()

    if static_path:
        # 设置 SPA 中间件
        setup_spa_middleware(app, static_path, exclude_paths=[prefix, "/docs", "/openapi.json"])
        
        # 挂载静态文件（作为后备）
        app.mount("/", StaticFiles(
            directory=str(static_path), 
            html=True
        ), name="static")

    @app.on_event("shutdown")
    async def cleanup():
        """
        应用关闭时清理资源
        """
        if static_manager:
            static_manager.cleanup()
        
        await zmq_client.close()
        await thread_manager_dealer.stop()
        await router.stop()

    return app
