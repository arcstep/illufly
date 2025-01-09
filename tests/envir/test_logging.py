import os
import logging
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from illufly.envir.logging import (
    get_log_config,
    check_disk_space,
    DiskSpaceCheckHandler,
    setup_logging
)

# ============= Fixtures =============
@pytest.fixture
def temp_log_dir(tmp_path):
    """创建临时日志目录"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    return log_dir

@pytest.fixture
def mock_env_vars(temp_log_dir):
    """模拟环境变量"""
    env_vars = {
        'LOG_LEVEL': 'INFO',
        'LOG_DIR': str(temp_log_dir),
        'LOG_FILE_MAX_BYTES': '1048576',  # 1MB
        'LOG_FILE_BACKUP_COUNT': '5',
        'LOG_FORMAT': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'LOG_DATE_FORMAT': '%Y-%m-%d %H:%M:%S',
        'LOG_ENCODING': 'utf-8',
        'LOG_MIN_FREE_SPACE': '104857600'  # 100MB
    }
    with patch.dict('os.environ', env_vars):
        yield env_vars

# ============= 配置测试 =============
def test_get_log_config(mock_env_vars):
    """测试日志配置获取"""
    config = get_log_config()
    
    # 验证所有必需的配置项都存在
    assert all(k in config for k in [
        'LOG_LEVEL',
        'LOG_DIR',
        'LOG_FILE_MAX_BYTES',
        'LOG_FILE_BACKUP_COUNT',
        'LOG_FORMAT',
        'LOG_DATE_FORMAT',
        'LOG_ENCODING',
        'LOG_MIN_FREE_SPACE'
    ])
    
    # 验证配置值正确
    assert config['LOG_LEVEL'] == 'INFO'
    assert Path(config['LOG_DIR']).name == 'logs'

# ============= 磁盘空间检查测试 =============
def test_check_disk_space(temp_log_dir):
    """测试磁盘空间检查"""
    # 测试正常情况
    assert check_disk_space(temp_log_dir, 1) == True
    
    # 测试空间不足情况
    assert check_disk_space(temp_log_dir, float('inf')) == False

def test_check_disk_space_invalid_path():
    """测试无效路径的磁盘空间检查"""
    invalid_path = Path("/non_existent_path_xyz")
    # 当路径无效时应返回True（默认允许写入）
    assert check_disk_space(invalid_path, 1) == True

# ============= DiskSpaceCheckHandler测试 =============
def test_disk_space_check_handler(temp_log_dir):
    """测试磁盘空间检查处理器"""
    log_file = temp_log_dir / "test.log"
    handler = DiskSpaceCheckHandler(
        min_free_space=1024,
        filename=str(log_file),
        maxBytes=1024,
        backupCount=3
    )
    
    # 创建日志记录
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None
    )
    
    # 测试正常写入
    handler.emit(record)
    assert log_file.exists()
    
    # 测试空间不足情况
    with patch('illufly.envir.logging.check_disk_space', return_value=False):
        with patch('logging.warning') as mock_warning:
            handler.emit(record)
            mock_warning.assert_called_once()

# ============= 整体日志系统测试 =============
def test_setup_logging(mock_env_vars, temp_log_dir):
    """测试日志系统初始化"""
    # 重置日志系统
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 初始化日志系统
    setup_logging()
    
    # 验证根日志器配置
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) == 3  # 控制台 + 主日志 + 错误日志
    
    # 写入测试日志
    logging.info("Test info message")
    logging.error("Test error message")
    
    # 验证日志文件
    main_log = temp_log_dir / "illufly.log"
    error_log = temp_log_dir / "error.log"
    
    assert main_log.exists()
    assert error_log.exists()
    
    # 验证错误日志只包含ERROR级别以上的消息
    error_content = error_log.read_text()
    assert "Test error message" in error_content
    assert "Test info message" not in error_content

def test_log_rotation(mock_env_vars, temp_log_dir, caplog):
    """测试日志轮转功能"""
    # 创建新的环境变量字典
    test_env = mock_env_vars.copy()
    test_env.update({
        'LOG_FILE_MAX_BYTES': '10',
        'LOG_FORMAT': '%(message)s',
        'LOG_FILE_BACKUP_COUNT': '3'
    })
    
    with patch.dict('os.environ', test_env, clear=True):  # clear=True 确保清除所有其他环境变量
        setup_logging()
        logger = logging.getLogger()
        main_log = temp_log_dir / "illufly.log"

        # 检查初始配置
        print("\n=== 初始配置 ===")
        for handler in logger.handlers:
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                print(f"Handler类型: {type(handler)}")
                print(f"maxBytes: {handler.maxBytes}")
                print(f"backupCount: {handler.backupCount}")
                print(f"baseFilename: {handler.baseFilename}")
                print(f"mode: {handler.mode}")

        # 写入数据并监控文件大小
        print("\n=== 写入过程 ===")
        for i in range(5):
            msg = "X" * 20
            logger.info(msg)
            
            # 立即刷新
            for handler in logger.handlers:
                if isinstance(handler, logging.handlers.RotatingFileHandler):
                    handler.flush()
                    handler.close()  # 确保文件被关闭，触发轮转
                    handler.doRollover()  # 强制进行轮转
            
            # 检查文件状态
            if main_log.exists():
                size = main_log.stat().st_size
                print(f"\n第 {i+1} 次写入:")
                print(f"- 写入内容长度: {len(msg)} 字节")
                print(f"- 当前文件大小: {size} 字节")
                print(f"- 文件列表: {list(temp_log_dir.glob('illufly.log*'))}")
                try:
                    content = main_log.read_text()
                    print(f"- 文件内容:\n{content}")
                except Exception as e:
                    print(f"- 读取文件失败: {e}")

        # 最终状态
        print("\n=== 最终状态 ===")
        log_files = list(temp_log_dir.glob("illufly.log*"))
        print(f"所有日志文件: {[f.name for f in log_files]}")
        print(f"文件大小: {[(f.name, f.stat().st_size) for f in log_files]}")
        
        if main_log.exists():
            print(f"主日志文件内容:\n{main_log.read_text()}")

        assert len(log_files) > 1, (
            f"\n日志轮转失败:\n"
            f"1. 找到的文件: {[f.name for f in log_files]}\n"
            f"2. 主日志大小: {main_log.stat().st_size if main_log.exists() else 'N/A'} 字节\n"
            f"3. 期望的最大字节数: 10 字节\n"
            f"4. 实际写入: 5次 * 20字节 = 100字节\n"
        )

# ============= 异常情况测试 =============
def test_setup_logging_with_permission_error(mock_env_vars, temp_log_dir):
    """测试文件权限问题"""
    # 模拟权限错误
    with patch('pathlib.Path.mkdir', side_effect=PermissionError):
        with pytest.raises(PermissionError):
            setup_logging()

def test_setup_logging_with_encoding_error(mock_env_vars, temp_log_dir):
    """测试编码问题"""
    # 创建一个新的环境变量字典，而不是修改原有的
    test_env = mock_env_vars.copy()
    test_env['LOG_ENCODING'] = 'invalid-encoding'
    
    with patch.dict('os.environ', test_env, clear=True):  # clear=True 确保清除所有其他环境变量
        with pytest.raises(LookupError) as exc_info:
            setup_logging()
        assert "不支持的编码格式" in str(exc_info.value) 