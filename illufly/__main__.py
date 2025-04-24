import click
import uvicorn
import logging
import asyncio
import signal
import os
import traceback
import sys

from voidrail import ServiceRouter
from .api.start import create_app

# 初始化最基础的日志配置
# logging.basicConfig(
#     format='[%(levelname)s] %(message)s',
#     level=logging.INFO
# )
logger = logging.getLogger("illufly")

# def configure_logging(debug_mode, log_level):
#     """独立配置日志系统"""
#     level = logging.DEBUG if debug_mode else getattr(logging, log_level.upper())
#     formatter = logging.Formatter(
#         '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#         datefmt='%Y-%m-%d %H:%M:%S'
#     )
    
#     # 清除所有现有处理器
#     for handler in logging.root.handlers[:]:
#         logging.root.removeHandler(handler)
    
#     # 添加新的流处理器
#     stream_handler = logging.StreamHandler()
#     stream_handler.setFormatter(formatter)
#     stream_handler.setLevel(level)
    
#     logging.root.addHandler(stream_handler)
#     logging.root.setLevel(level)

def validate_base_url(ctx, param, value):
    """自动生成base_url的验证逻辑"""
    if not value:
        host = ctx.params.get('host', '0.0.0.0')
        port = ctx.params.get('port', 8000)
        prefix = ctx.params.get('prefix', '/api').rstrip('/')
        return f"http://{host}:{port}{prefix}"
    return value

@click.command()
@click.option('--data-dir', default='./.data', help='数据目录 (默认: ./.data)')
@click.option('--host', default='0.0.0.0', help='服务主机地址 (默认: 0.0.0.0)')
@click.option('--port', default=8000, type=int, help='服务端口 (默认: 8000)')
@click.option('--title', default='Illufly API', help='API标题 (默认: Illufly API)')
@click.option('--description', default='Illufly 后端 API 服务', help='API描述')
@click.option('--prefix', default='/api', help='API路由前缀 (默认: /api)')
@click.option('--router-address', default='tcp://127.0.0.1:31571', help='ZMQ路由地址')
@click.option('--ssl-keyfile', help='SSL密钥文件路径')
@click.option('--ssl-certfile', help='SSL证书文件路径')
@click.option('--static-dir', help='静态文件目录')
@click.option('--cors-origins', multiple=True, help='CORS允许的源地址')
@click.option('--log-level', 
             type=click.Choice(['debug', 'info', 'warning', 'error', 'critical'], case_sensitive=False),
             default='info',
             help='日志级别')
@click.option('--debug', is_flag=True, help='启用调试模式')
def main(
    data_dir, host, port, title, description, prefix, 
    router_address, ssl_keyfile, ssl_certfile, static_dir, cors_origins, log_level, debug
):
    """启动Illufly API服务"""
    try:
        # 优先配置日志系统
        # configure_logging(debug, log_level)
        logger.info("=== 服务启动初始化 ===")
        
        # 打印测试信息验证日志通道
        print("控制台打印测试")
        logger.debug("调试日志测试")
        logger.info("信息日志测试")
        
        # 立即验证参数处理
        logger.debug("解析后的参数：%s", locals())

        # 运行异步服务
        asyncio.run(start_server(
            data_dir, host, port, title, description, prefix,
            router_address, ssl_keyfile, ssl_certfile, static_dir, cors_origins
        ))
        
    except Exception as e:
        logger.critical("主程序崩溃：%s", str(e), exc_info=True)
        sys.exit(1)

async def start_server(
    data_dir, host, port, title, description, prefix, 
    router_address, ssl_keyfile, ssl_certfile, static_dir, cors_origins
):
    """启动服务的异步逻辑"""
    try:
        logger.info("正在创建应用实例...")
        router = ServiceRouter(router_address)
        await router.start()

        app = await create_app(
            data_dir=data_dir,
            title=title,
            description=description,
            prefix=prefix,
            static_dir=static_dir,
            cors_origins=cors_origins
        )

        # 配置uvicorn时禁用所有内部日志处理
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            log_level=None,  # 完全禁用uvicorn日志
            access_log=False  # 禁用访问日志
        )
        
        server = uvicorn.Server(config)
        
        # 信号处理
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(shutdown_handler(server))
            )

        logger.info("服务启动成功")
        await server.serve()
        
    except Exception as e:
        logger.error("服务启动失败：%s", str(e), exc_info=True)
        raise

async def shutdown_handler(server):
    """带日志记录的关闭处理"""
    logger.info("收到终止信号，正在关闭服务...")
    await server.shutdown()
    logger.info("服务已正常终止")

if __name__ == "__main__":
    # 全局异常捕获
    sys.excepthook = lambda typ, val, tb: (
        logging.critical("未捕获异常", exc_info=(typ, val, tb))
    )
    main() 