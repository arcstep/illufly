import logging
import json
import threading
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import contextmanager
import time
import atexit

from .base import StorageBackend, DateTimeEncoder


class JSONSerializationError(Exception):
    """JSON序列化错误"""
    pass


class BufferedJSONFileStorageBackend(StorageBackend):
    """带写缓冲的JSON文件存储后端"""
    
    def __init__(
        self, 
        data_dir: str = None, 
        segment: str = None,
        flush_interval: int = 60,
        flush_threshold: int = 1000,
        logger = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir) if data_dir else get_env("ILLUFLY_JIAOZI_CACHE_STORE_DIR")
        self._segment = segment or "data.json"
        
        # 写缓冲相关
        self._memory_buffer = {}
        self._dirty_owners = set()
        self._modify_count = 0
        self._last_flush_time = time.time()
        self._flush_interval = flush_interval
        self._flush_threshold = flush_threshold
        
        # 线程安全
        self._buffer_lock = threading.RLock()
        self._flush_timer = None
        self._should_stop = False
        self._is_flushing = False  # 添加刷新状态标志
        
        self.logger.info(
            "初始化存储后端: dir=%s, segment=%s, interval=%d, threshold=%d",
            self._data_dir, self._segment, flush_interval, flush_threshold
        )
        
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._start_flush_timer()
            atexit.register(self._flush_on_exit)
        except Exception as e:
            self.logger.critical("初始化失败: %s", str(e), exc_info=True)
            raise

        self._encoder = json.JSONEncoder(
            ensure_ascii=False,
            default=self._json_default
        )

    def _json_default(self, obj: Any) -> Any:
        """自定义JSON序列化处理"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, 'to_dict'):
            return obj.to_dict()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        raise JSONSerializationError(
            f"无法序列化类型 {type(obj).__name__}"
        )

    def list_owners(self) -> List[str]:
        """列出所有数据所有者ID"""
        with self._buffer_lock:
            # 首先获取内存中的所有owner_id
            memory_owners = set(self._memory_buffer.keys())
            
            # 如果有文件，读取文件中的owner_id
            file_path = self._data_dir / self._segment
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                        file_owners = set(file_data.keys())
                except Exception as e:
                    self.logger.error("读取文件失败: %s", e)
                    file_owners = set()
            else:
                file_owners = set()
            
            # 合并内存和文件中的owner_id，并排除已删除的
            all_owners = (memory_owners | file_owners) - {
                owner_id for owner_id in self._memory_buffer 
                if self._memory_buffer[owner_id] is None
            }
            
            self.logger.debug(
                "列出所有owner: memory=%d, file=%d, total=%d", 
                len(memory_owners), len(file_owners), len(all_owners)
            )
            return sorted(all_owners)  # 返回排序后的列表

    def get(self, owner_id: str) -> Optional[Any]:
        """获取数据，优先从内存缓冲区读取"""
        with self._buffer_lock:
            # 先检查内存缓冲区
            if owner_id in self._memory_buffer:
                value = self._memory_buffer[owner_id]
                if value is None:  # 标记为删除的数据
                    return None
                self.logger.debug("从内存缓冲区读取: owner_id=%s", owner_id)
                return value
        
        # 从文件读取
        file_path = self._data_dir / self._segment
        if not file_path.exists():
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get(owner_id)
        except Exception as e:
            self.logger.error("读取文件失败: owner_id=%s, error=%s", owner_id, e)
            return None

    def set(self, owner_id: str, data: Any) -> None:
        """写入数据到内存缓冲区"""
        if data is None:
            self.logger.debug("跳过空数据写入: owner_id=%s", owner_id)
            return
            
        # 验证数据是否可序列化
        try:
            json.dumps(data, default=self._json_default)
        except Exception as e:
            self.logger.error("数据序列化失败: %s", e)
            raise JSONSerializationError(f"数据无法序列化: {e}")

        with self._buffer_lock:
            self._memory_buffer[owner_id] = data
            self._dirty_owners.add(owner_id)
            self._modify_count += 1
            
            should_flush = (
                self._modify_count >= self._flush_threshold or 
                time.time() - self._last_flush_time >= self._flush_interval
            )
        
        if should_flush:
            self._flush_to_disk()

    def delete(self, owner_id: str) -> bool:
        """删除数据"""
        with self._buffer_lock:
            # 在内存缓冲区中标记为删除（使用None值）
            if owner_id in self._memory_buffer or self.get(owner_id) is not None:
                self._memory_buffer[owner_id] = None
                self._dirty_owners.add(owner_id)
                self._modify_count += 1
                return True
            return False

    def _flush_to_disk(self):
        """将缓冲区数据写入磁盘"""
        if self._is_flushing:
            self.logger.debug("已有刷新操作在进行中")
            return
            
        try:
            self._is_flushing = True
            
            with self._buffer_lock:
                if not self._dirty_owners:
                    return
                
                # 准备要写入的数据
                file_path = self._data_dir / self._segment
                current_data = {}
                dirty_data = {}
                
                # 复制需要处理的数据
                for owner_id in self._dirty_owners:
                    if owner_id in self._memory_buffer:
                        dirty_data[owner_id] = self._memory_buffer[owner_id]
            
            # 在锁外读取文件
            if file_path.exists():
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                except json.JSONDecodeError as e:
                    self.logger.error("读取文件格式错误: %s", e)
                    current_data = {}
                except Exception as e:
                    self.logger.error("读取文件失败: %s", e)
                    current_data = {}
            
            # 合并数据
            for owner_id, value in dirty_data.items():
                if value is None:
                    current_data.pop(owner_id, None)
                else:
                    current_data[owner_id] = value
            
            # 写入文件
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(
                        current_data, 
                        f, 
                        ensure_ascii=False, 
                        indent=2,
                        default=self._json_default
                    )
            except Exception as e:
                self.logger.error("写入文件失败: %s", e)
                raise
            
            # 更新状态
            with self._buffer_lock:
                self._dirty_owners.clear()
                self._modify_count = 0
                self._last_flush_time = time.time()
                
        finally:
            self._is_flushing = False

    def _start_flush_timer(self):
        """启动定时刷新计时器"""
        if self._should_stop:
            return
            
        def _timer_callback():
            if not self._should_stop and not self._is_flushing:
                try:
                    self._flush_to_disk()
                except Exception as e:
                    self.logger.error("定时刷新失败: %s", e)
                finally:
                    if not self._should_stop:
                        self._start_flush_timer()
        
        if self._flush_timer:
            self._flush_timer.cancel()
        
        self._flush_timer = threading.Timer(self._flush_interval, _timer_callback)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush_on_exit(self):
        """程序退出时的清理工作"""
        self._should_stop = True  # 设置停止标志
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_to_disk()

    def close(self):
        """关闭存储后端"""
        self._should_stop = True
        if self._flush_timer:
            self._flush_timer.cancel()
        self._flush_to_disk()  # 最后一次刷新