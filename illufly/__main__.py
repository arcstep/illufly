import uvicorn
import logging
import argparse
import asyncio
import signal
import os

from .api.start import create_app

def _parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Illufly API 服务")
    arguments = [
        ("--db-path", "./db", "数据库路径 (默认: ./db)"),
        ("--provider", None, "兼容 LiteLLM 的服务提供者 (默认: OPENAI)"),
        ("--openai", None, "OpenAI模仿者列表 (默认: OPENAI)"),
        ("--router-address", None, "ZMQ 路由地址 (默认: inproc://router-bus)"),
        ("--title", "Illufly API", "API 标题 (默认: Illufly API)"),
        ("--description", "Illufly 后端 API 服务", "API 描述"),
        ("--prefix", "/api", "API 路由前缀 (默认: /api)"),
        ("--base_url", "http://127.0.0.1:8000/api", "OpenAI兼容接口 路由前缀 (默认: http://127.0.0.1:8000/api)"),
        ("--host", "0.0.0.0", "服务主机地址 (默认: 0.0.0.0)"),
        ("--port", 8000, "服务端口 (默认: 8000)"),
        ("--ssl-keyfile", None, "SSL 密钥文件路径"),
        ("--ssl-certfile", None, "SSL 证书文件路径"),
        ("--static-dir", None, "静态文件目录 (默认: 包内 static 目录)"),
        ("--cors-origins", None, "CORS 服务地址列表，例如 http://localhost:3000"),
        ("--log-level", "info", "日志级别 (默认: info)"),
    ]
    
    for arg, default, help in arguments:
        if arg in ["--cors-origins"]:
            # 特殊处理 cors-origins 参数，支持多个参数值
            parser.add_argument(arg, nargs='+', default=default, help=help)
        else:
            parser.add_argument(arg, default=default, help=help)

    args = parser.parse_args()
    
    # 将字符串日志级别转换为 logging 常量
    args.log_level = getattr(logging, args.log_level.upper())

    # 将 port 转为 int
    args.port = int(args.port)
    
    return args

async def main():
    """主函数"""
    args = _parse_args()
    os.environ['LOG_LEVEL'] = str(args.log_level)
    
    app = await create_app(
        db_path=args.db_path,
        openai_imitator=args.openai,
        provider=args.provider,
        title=args.title,
        description=args.description,
        prefix=args.prefix,
        base_url=args.base_url,
        static_dir=args.static_dir,
        cors_origins=args.cors_origins
    )

    config = uvicorn.Config(    
        app,
        host=args.host,
        port=args.port,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
        log_level=args.log_level
    )
    server = uvicorn.Server(config)

    # 设置信号处理
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(server.shutdown(), name="uvicorn-shutdown")
        )
    
    # 启动服务器
    await server.serve()


if __name__ == "__main__":
    """
    启动illufly api服务。

    使用方法：
    # HTTP 开发环境
    poetry run python -m illufly --ui-origins http://localhost:3000

    # HTTPS 开发环境
    poetry run python -m illufly \
    --ui-origins https://localhost:3000 \
    --ssl-keyfile ./certs/key.pem \
    --ssl-certfile ./certs/cert.pem

    # 生产环境（同时支持 HTTP 和 HTTPS）
    poetry run python -m illufly \
    --ui-origins http://ui.example.com https://ui.example.com \
    --ssl-keyfile /etc/ssl/private/example.key \
    --ssl-certfile /etc/ssl/certs/example.crt

    查看帮助：
    poetry run python -m illufly --help

    """
    asyncio.run(main()) 