from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import argparse
from pathlib import Path
from typing import Optional

from ...rocksdb import IndexedRocksDB
from .tokens import TokensManager
from .users import UsersManager
from .endpoints import create_auth_endpoints

def create_logger(log_level: int = logging.INFO) -> logging.Logger:
    """创建日志记录器
    
    Args:
        log_level: 日志级别（使用 logging 模块的常量）
    """
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)

    # 添加处理器到 logger
    logger.addHandler(console_handler)

    return logger

def create_app(
    db_path: str = "./data/db",
    title: str = "Illufly API",
    description: str = "Illufly 后端 API 服务",
    version: str = "0.1.0",
    prefix: str = "/api",
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

    logger = create_logger(log_level)

    app = FastAPI(
        title=title,
        description=description,
        version=version
    )

    # 配置 CORS
    origins = [
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        # 添加其他允许的源
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
    db = IndexedRocksDB(str(db_path), logger=logger)

    # 初始化管理器
    tokens_manager = TokensManager(db, logger=logger)
    users_manager = UsersManager(db, logger=logger)

    # 获取路由处理函数字典
    route_handlers = create_auth_endpoints(
        app=app,
        tokens_manager=tokens_manager,
        users_manager=users_manager,
        prefix=prefix,
        logger=logger
    )

    # 注册路由
    for _, (method, path, handler) in route_handlers.items():
        getattr(app, method)(path)(handler)

    @app.get("/")
    async def root():
        """根路由"""
        return {
            "message": "欢迎使用 Illufly API",
            "version": version
        }

    return app

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Illufly API 服务")
    
    parser.add_argument(
        "--db-path",
        default="./data/db",
        help="数据库路径 (默认: ./data/db)"
    )
    parser.add_argument(
        "--title",
        default="Illufly API",
        help="API 标题 (默认: Illufly API)"
    )
    parser.add_argument(
        "--description",
        default="Illufly 后端 API 服务",
        help="API 描述"
    )
    parser.add_argument(
        "--version",
        default="0.1.0",
        help="API 版本 (默认: 0.1.0)"
    )
    parser.add_argument(
        "--prefix",
        default="/api",
        help="API 路由前缀 (默认: /api)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="服务主机地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="服务端口 (默认: 8000)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载 (开发模式)"
    )
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="日志级别 (默认: info)"
    )
    
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
        version=args.version,
        prefix=args.prefix,
        log_level=args.log_level  # 现在是 logging 常量
    )
    
    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level  # uvicorn 需要字符串形式的日志级别
    )

if __name__ == "__main__":
    main()