import uvicorn
import logging
import argparse

from .api.start import create_app

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
        ("--ssl-keyfile", None, "SSL 密钥文件路径"),
        ("--ssl-certfile", None, "SSL 证书文件路径"),
        ("--static-dir", None, "静态文件目录 (默认: 包内 static 目录)"),
        ("--ui-origins", "+", "UI 服务地址列表，例如 http://localhost:3000"),
        ("--log-level", "info", "日志级别 (默认: info)"),
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
        static_dir=args.static_dir,
        ui_origins=args.ui_origins,
        log_level=args.log_level
    )
    
    # 启动服务
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        ssl_keyfile=args.ssl_keyfile,
        ssl_certfile=args.ssl_certfile,
        log_level=args.log_level
    )

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
    main() 