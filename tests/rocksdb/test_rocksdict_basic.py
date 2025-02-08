import pytest
import logging
import tempfile
import shutil
import time
from pathlib import Path
from speedict import (
    Rdict, 
    Options, 
    ReadOptions,
    PlainTableFactoryOptions,
    KeyEncodingType,
    SliceTransform
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.INFO)

@pytest.fixture
def db_path():
    """创建临时数据库路径"""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_db"
    yield db_path
    if temp_dir.exists():
        time.sleep(0.1)
        shutil.rmtree(temp_dir)

@pytest.fixture
def db(db_path):
    """创建并初始化数据库，配置前缀支持"""
    # 配置数据库选项
    opts = Options()
    
    # 设置前缀提取器 - 使用固定长度前缀
    # "user:xx" 的前缀长度是5 ("user:")
    opts.set_prefix_extractor(SliceTransform.create_fixed_prefix(5))
    
    # 配置表选项
    table_opts = PlainTableFactoryOptions()
    table_opts.encoding_type = KeyEncodingType.prefix()
    table_opts.bloom_bits_per_key = 10
    table_opts.hash_table_ratio = 0.75
    table_opts.index_sparseness = 16
    opts.set_plain_table_factory(table_opts)
    
    # 创建数据库实例
    db = Rdict(str(db_path), opts)
    
    # 写入测试数据
    test_data = {
        **{f"user:{i:02d}": f"user_{i:02d}" for i in range(1, 11)},
        **{f"config:{i:02d}": f"config_{i:02d}" for i in range(1, 6)},
        **{f"log:{i:02d}": f"log_{i:02d}" for i in range(1, 6)}
    }
    for k, v in test_data.items():
        db[k] = v
        logger.info(f"Added: {k} = {v}")
    
    yield db
    
    db.close()
    time.sleep(0.1)
    try:
        Rdict.destroy(str(db_path), Options())
    except Exception as e:
        logger.warning(f"销毁数据库时出错: {e}")

def test_prefix_iteration(db):
    """测试前缀迭代
    
    目标：验证 set_prefix_same_as_start 的行为
    1. 基本的前缀匹配
    2. 不同位置的seek
    3. 前缀边界情况
    """
    logger.info("\n=== 测试前缀迭代 ===")
    
    # 1. 基本前缀匹配
    logger.info("\n1. 基本前缀匹配:")
    opts = ReadOptions()
    opts.set_prefix_same_as_start(True)
    it = db.iter(opts)
    
    it.seek("user:")
    items = []
    while it.valid():
        key = it.key()
        if not key.startswith("user:"):
            break
        items.append((key, it.value()))
        it.next()
    
    logger.info(f"Found {len(items)} items with prefix 'user:':")
    for k, v in items:
        logger.info(f"{k} = {v}")
    
    assert len(items) == 10, "应该找到10个user:前缀的项"
    assert all(k.startswith("user:") for k, _ in items), "所有key应该以user:开头"
    assert items[0][0] == "user:01", "应该从user:01开始"
    assert items[-1][0] == "user:10", "应该在user:10结束"
    
    # 2. 从中间位置seek
    logger.info("\n2. 从中间位置seek:")
    it.seek("user:05")
    mid_items = []
    while it.valid():
        key = it.key()
        if not key.startswith("user:"):
            break
        mid_items.append((key, it.value()))
        it.next()
    
    logger.info(f"Found {len(mid_items)} items from 'user:05':")
    for k, v in mid_items:
        logger.info(f"{k} = {v}")
    
    assert mid_items[0][0] == "user:05", "应该从user:05开始"
    assert len(mid_items) == 6, "应该找到6个项(05-10)"
    
    # 3. 不同前缀
    logger.info("\n3. 测试其他前缀:")
    it.seek("config:")
    config_items = []
    while it.valid():
        key = it.key()
        if not key.startswith("config:"):
            break
        config_items.append((key, it.value()))
        it.next()
    
    logger.info(f"Found {len(config_items)} items with prefix 'config:':")
    for k, v in config_items:
        logger.info(f"{k} = {v}")
    
    assert len(config_items) == 5, "应该找到5个config:前缀的项"
    del it

def test_range_iteration(db):
    """测试范围迭代
    
    目标：验证范围查询的行为
    1. 使用seek定位到范围起点
    2. 手动检查范围边界
    3. 不同范围的查询
    """
    logger.info("\n=== 测试范围迭代 ===")
    
    # 1. 基本范围查询 [user:03, user:07)
    logger.info("\n1. 基本范围查询:")
    it = db.iter()
    
    items = []
    it.seek("user:03")  # 直接定位到起点
    while it.valid():
        key = it.key()
        if key >= "user:07":  # 手动检查上界
            break
        if not key.startswith("user:"):  # 确保在同一前缀
            break
        items.append((key, it.value()))
        it.next()
    
    logger.info(f"Range [user:03, user:07) found {len(items)} items:")
    for k, v in items:
        logger.info(f"{k} = {v}")
    
    assert len(items) == 4, "应该找到4个项"
    assert [k for k, _ in items] == [
        "user:03", "user:04", "user:05", "user:06"
    ], "应该包含正确的序列"
    
    # 2. 跨前缀范围查询
    logger.info("\n2. 跨前缀范围查询:")
    it.seek("config:03")
    cross_items = []
    while it.valid():
        key = it.key()
        if key >= "log:":  # 在log:前缀之前停止
            break
        cross_items.append((key, it.value()))
        it.next()
    
    logger.info(f"Range [config:03, log:) found {len(cross_items)} items:")
    for k, v in cross_items:
        logger.info(f"{k} = {v}")
    
    assert len(cross_items) > 0, "应该找到一些项"
    assert all(k.startswith("config:") for k, _ in cross_items), "应该只包含config:前缀的项"
    
    del it

def test_combined_options(db):
    """测试选项组合
    
    目标：验证不同选项组合的行为
    1. 前缀 + 范围边界
    2. 不同的seek策略
    """
    logger.info("\n=== 测试选项组合 ===")
    
    opts = ReadOptions()
    opts.set_prefix_same_as_start(True)
    it = db.iter(opts)
    
    # 在前缀限制下的范围查询
    it.seek("user:03")
    items = []
    while it.valid():
        key = it.key()
        if not key.startswith("user:"):
            break
        if key >= "user:07":
            break
        items.append((key, it.value()))
        it.next()
    
    logger.info(f"Prefix-constrained range found {len(items)} items:")
    for k, v in items:
        logger.info(f"{k} = {v}")
    
    assert len(items) == 4, "应该找到4个项"
    assert all("user:03" <= k < "user:07" for k, _ in items), "应该在正确的范围内"
    
    del it 