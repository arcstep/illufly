"""日志配置模块
注意:
    1. 默认日志级别和输出格式由环境变量控制
    2. 日志会同时输出到控制台和文件
    3. error级别以上的日志会额外写入error.log
"""

import os
import logging
import logging.handlers
import shutil
from pathlib import Path
from typing import Dict, Any

from .default_env import get_env

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

def setup_logging(log_level=None):
    """初始化日志系统
    
    Args:
        log_level: 可选，直接指定日志级别，覆盖环境变量设置
    """
    config = get_log_config()
    
    # 允许外部直接指定日志级别
    if log_level:
        config['LOG_LEVEL'] = log_level.upper()
    
    # 验证编码
    try:
        import codecs
        codecs.lookup(config['LOG_ENCODING'])  # 这会直接检查编码名称是否有效
    except LookupError:
        raise LookupError(f"不支持的编码格式: {config['LOG_ENCODING']}")
    
    # 确保日志目录存在
    log_dir = Path(config['LOG_DIR'])
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 类型转换
    try:
        max_bytes = int(config['LOG_FILE_MAX_BYTES'])
        backup_count = int(config['LOG_FILE_BACKUP_COUNT'])
        min_free_space = int(config['LOG_MIN_FREE_SPACE'])
    except ValueError as e:
        raise ValueError(f"日志配置中的数值设置无效: {e}")
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config['LOG_LEVEL'].upper()))
    
    # 移除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 日志格式
    formatter = logging.Formatter(
        config['LOG_FORMAT'],
        datefmt=config['LOG_DATE_FORMAT']
    )
    
    # 添加处理器
    handlers = [
        logging.StreamHandler(),
        DiskSpaceCheckHandler(
            min_free_space=min_free_space,
            filename=str(log_dir / 'illufly.log'),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=config['LOG_ENCODING']
        ),
        DiskSpaceCheckHandler(
            min_free_space=min_free_space,
            filename=str(log_dir / 'error.log'),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=config['LOG_ENCODING']
        )
    ]
    
    for handler in handlers:
        handler.setFormatter(formatter)
        if isinstance(handler, logging.FileHandler) and 'error.log' in str(handler.baseFilename):
            handler.setLevel(logging.ERROR)
        root_logger.addHandler(handler)

    # 重置所有已创建的logger级别
    level = getattr(logging, config['LOG_LEVEL'].upper())
    for logger_name in logging.root.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)

# 不要在模块级别自动调用 setup_logging()
# 而是在 __init__.py 中提供此功能供导入
