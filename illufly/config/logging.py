import os
import logging
import logging.handlers
import shutil
from pathlib import Path
from typing import Dict, Any

from .base import get_env

def get_log_config() -> Dict[str, Any]:
    """获取日志配置，优先使用环境变量"""

    return {
        k: get_env(k)
        for k in [
            'LOG_LEVEL',
            'LOG_DIR',
            'LOG_FILE_MAX_BYTES',
            'LOG_FILE_BACKUP_COUNT',
            'LOG_FORMAT',
            'LOG_DATE_FORMAT',
            'LOG_ENCODING',
            'LOG_MIN_FREE_SPACE'
        ]
    }

def check_disk_space(log_dir: Path, min_free_space: int) -> bool:
    """检查磁盘剩余空间是否足够"""
    try:
        free_space = shutil.disk_usage(log_dir).free
        return free_space >= min_free_space
    except Exception as e:
        logging.error(f"检查磁盘空间时出错: {e}")
        return True  # 出错时默认允许写入

class DiskSpaceCheckHandler(logging.handlers.RotatingFileHandler):
    """带磁盘空间检查的日志处理器"""
    def __init__(self, min_free_space: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_free_space = min_free_space
        
    def emit(self, record):
        if check_disk_space(Path(self.baseFilename).parent, self.min_free_space):
            super().emit(record)
        else:
            # 磁盘空间不足时,记录一条警告
            logging.warning(f"磁盘剩余空间不足 {self.min_free_space} 字节,暂停日志写入")

def setup_logging():
    """初始化日志系统"""
    config = get_log_config()
    
    # 确保日志目录存在
    log_dir = Path(config['LOG_DIR'])
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config['LOG_LEVEL'].upper()))
    
    # 日志格式
    formatter = logging.Formatter(
        config['LOG_FORMAT'],
        datefmt=config['LOG_DATE_FORMAT']
    )
    
    # 添加处理器
    handlers = [
        # 1. 控制台输出
        logging.StreamHandler(),
        
        # 2. 主日志文件（按大小轮转,带磁盘空间检查）
        DiskSpaceCheckHandler(
            min_free_space=config['LOG_MIN_FREE_SPACE'],
            filename=log_dir / 'illufly.log',
            maxBytes=config['LOG_FILE_MAX_BYTES'],
            backupCount=config['LOG_FILE_BACKUP_COUNT'],
            encoding=config['LOG_ENCODING']
        ),
        
        # 3. 错误日志文件（按大小轮转,带磁盘空间检查）
        DiskSpaceCheckHandler(
            min_free_space=config['LOG_MIN_FREE_SPACE'],
            filename=log_dir / 'error.log',
            maxBytes=config['LOG_FILE_MAX_BYTES'],
            backupCount=config['LOG_FILE_BACKUP_COUNT'],
            encoding=config['LOG_ENCODING']
        )
    ]
    
    # 配置处理器
    for handler in handlers:
        handler.setFormatter(formatter)
        if isinstance(handler, logging.FileHandler) and 'error.log' in str(handler.baseFilename):
            handler.setLevel(logging.ERROR)
        root_logger.addHandler(handler)
    
    # 设置一些模块的默认日志级别
    logging.getLogger('illufly.io.jiaozi_cache').setLevel(
        getattr(logging, config['LOG_LEVEL'].upper())
    )

# 使用示例
if __name__ == "__main__":
    # 设置环境变量（通常在部署时设置）
    """
    export ILLUFLY_LOG_LEVEL=DEBUG
    export ILLUFLY_LOG_DIR=/var/log/illufly
    export ILLUFLY_LOG_FILE_MAX_BYTES=20971520  # 20MB
    export ILLUFLY_LOG_FILE_BACKUP_COUNT=10
    export ILLUFLY_LOG_MIN_FREE_SPACE=104857600  # 100MB
    """
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.debug("Debug message")
    logger.info("Info message")
    logger.error("Error message") 