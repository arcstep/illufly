from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional

import uvicorn
import logging
import argparse
import importlib.resources
import tempfile
import shutil

from ..__version__ import __version__
from ..rocksdb import IndexedRocksDB
from .auth.tokens import TokensManager
from .auth.users import UsersManager
from .auth.api_keys import ApiKeysManager
from .auth.endpoints import create_auth_endpoints
from .openai.endpoints import create_openai_endpoints
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

def mount_static_files(app: FastAPI, static_path: Optional[Path], logger: logging.Logger):
    """挂载静态文件"""
    if not static_path or not static_path.exists():
        logger.error("静态文件未找到")
        return
        
    try:
        app.mount("/", StaticFiles(
            directory=str(static_path), 
            html=True
        ), name="static")
        logger.info(f"FastAPI 静态资源已挂载: {static_path}")

    except Exception as e:
        logger.error(f"静态文件挂载失败: {e}")

def create_app(
    db_path: str = "./db",
    title: str = "Illufly API",
    description: str = "Illufly 后端 API 服务",
    prefix: str = "/api",
    host: str = "0.0.0.0",
    port: int = 8000,
    static_dir: str = None,
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
    origins = [f"http://{host}:{port}"]
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

    # 初始化数据管理实例
    tokens_manager = TokensManager(db, logger=logger)
    users_manager = UsersManager(db, logger=logger)
    api_keys_manager = ApiKeysManager(db, logger=logger)

    # 用户管理和认证路由
    auth_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        users_manager=users_manager,
        api_keys_manager=api_keys_manager,
        prefix=prefix,
        logger=logger
    )
    for _, (method, path, handler) in auth_handlers.items():
        getattr(app, method)(path)(handler)

    # OpenAI 路由
    openai_handlers = create_openai_endpoints(
        app=app,
        api_keys_manager=api_keys_manager,
        prefix=prefix,
        logger=logger
    )
    for _, (method, path, handler) in openai_handlers.items():
        getattr(app, method)(path)(handler)

    # 加载静态资源环境
    if Path(__file__).parent.joinpath("static").exists() and static_dir is None:
        static_path = Path(__file__).parent.joinpath("static")
    else:
        static_manager = StaticFilesManager(static_dir=static_dir, logger=logger)
        static_path = static_manager.setup()
        # FastAPI 关闭时清理临时目录
        @app.on_event("shutdown")
        async def cleanup_static():
            """应用关闭时清理静态文件"""
            static_manager.cleanup()

    mount_static_files(app, static_path, logger)

    return app

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Illufly API 服务")
    arguments = [
        ("--db-path", "./db", "数据库路径 (默认: ./db)"),
        ("--title", "Illufly API", "API 标题 (默认: Illufly API)"),
        ("--description", "Illufly 后端 API 服务", "API 描述"),
        ("--prefix", "/api", "API 路由前缀 (默认: /api)"),
        ("--host", "0.0.0.0", "服务主机地址 (默认: 0.0.0.0)"),
        ("--port", 8000, "服务端口 (默认: 8000)"),
        ("--log-level", "info", "日志级别 (默认: info)"),
        ("--static-dir", None, "静态文件目录 (默认: 包内 static 目录)")
    ]
    for arg, default, help in arguments:
        parser.add_argument(arg, default=default, help=help)

    args = parser.parse_args()
    
    # 将字符串日志级别转换为 logging 常量
    args.log_level = getattr(logging, args.log_level.upper())
    
    return args

def main():
    """主函数"""
    args = parse_args()
    
    app = create_app(
        db_path=args.db_path,
        title=args.title,
        description=args.description,
        prefix=args.prefix,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        static_dir=args.static_dir
    )
    
    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level
    )

if __name__ == "__main__":
    main()