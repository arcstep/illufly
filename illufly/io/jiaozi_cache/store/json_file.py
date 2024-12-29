import logging
import json
import threading
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime
from abc import ABC, abstractmethod
from contextlib import contextmanager

from .base import StorageBackend, DateTimeEncoder


class JSONFileStorageBackend(StorageBackend):
    def __init__(self, data_dir: str=None, segment: str=None, logger=None):
        self.logger = logger or logging.getLogger(__name__)
        self._data_dir = Path(data_dir) if data_dir else get_env("ILLUFLY_JIAOZI_CACHE_STORE_DIR")
        self._segment = segment or "data.json"
        self._file_locks = {}
        self._file_locks_lock = threading.Lock()
        
        # 确保数据目录存在
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("初始化存储后端: dir=%s, segment=%s", data_dir, segment)
        except Exception as e:
            self.logger.critical("创建数据目录失败: %s", str(e), exc_info=True)
            raise

    def get(self, owner_id: str) -> Optional[Any]:
        """从文件中读取数据"""
        file_path = self._get_file_path(owner_id)
        self.logger.debug("尝试读取文件: %s", file_path)
        
        if not file_path.exists():
            self.logger.debug("文件不存在: %s", file_path)
            return None

        with self._get_file_lock(owner_id):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 反序列化时处理 datetime
                    for key, value in data.items():
                        if isinstance(value, str) and self._is_iso_format(value):
                            try:
                                data[key] = datetime.fromisoformat(value)
                            except ValueError as e:
                                self.logger.warning(
                                    "日期格式转换失败: key=%s, value=%s, error=%s",
                                    key, value, str(e)
                                )
                    self.logger.debug("成功读取数据: owner_id=%s, keys=%s", 
                                    owner_id, list(data.keys()))
                    return data
            except json.JSONDecodeError as e:
                self.logger.error("JSON解析错误: %s, file=%s", str(e), file_path)
                return None
            except Exception as e:
                self.logger.error("读取文件失败: %s, file=%s", str(e), file_path, 
                                exc_info=True)
                return None

    def _is_iso_format(self, value: str) -> bool:
        """检查字符串是否为 ISO 格式"""
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False

    def set(self, owner_id: str, data: Any) -> None:
        """将数据保存到文件"""
        file_path = self._get_file_path(owner_id)
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error("创建目录失败: %s, path=%s", 
                            str(e), file_path.parent, exc_info=True)
            raise
        
        with self._get_file_lock(owner_id):
            try:
                if data is None:
                    self.logger.debug("跳过空数据写入: owner_id=%s", owner_id)
                    return
                    
                self.logger.debug("开始写入数据: owner_id=%s, path=%s", 
                                owner_id, file_path)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, 
                            cls=DateTimeEncoder)
                self.logger.debug("数据写入完成: owner_id=%s", owner_id)
                    
            except (TypeError, ValueError) as e:
                self.logger.error("数据序列化失败: %s, owner_id=%s", 
                                str(e), owner_id)
                raise
            except Exception as e:
                self.logger.error("写入文件失败: %s, file=%s", 
                                str(e), file_path, exc_info=True)
                raise

    def delete(self, owner_id: str) -> bool:
        """删除文件"""
        file_path = self._get_file_path(owner_id)
        self.logger.info("尝试删除文件: owner_id=%s, path=%s", owner_id, file_path)
        
        if not file_path.exists():
            self.logger.debug("文件不存在，无需删除: %s", file_path)
            return False
            
        with self._get_file_lock(owner_id):
            try:
                file_path.unlink()
                self.logger.info("文件删除成功: %s", file_path)
                return True
            except Exception as e:
                self.logger.error("删除文件失败: %s, file=%s", 
                                str(e), file_path, exc_info=True)
                return False

    def list_owners(self) -> List[str]:
        """列出所有的所有者ID"""
        try:
            self.logger.debug("开始列举所有者ID: dir=%s", self._data_dir)
            
            if not self._data_dir.exists():
                self.logger.debug("数据目录不存在: %s", self._data_dir)
                return []
            
            owners = [
                owner_dir.name 
                for owner_dir in self._data_dir.iterdir() 
                if owner_dir.is_dir() and 
                owner_dir.name != '.indexes' and  # 排除 .indexes 目录
                (owner_dir / self._segment).exists()
            ]
            
            self.logger.debug("找到 %d 个所有者", len(owners))
            return owners
            
        except Exception as e:
            self.logger.error("列举所有者失败: %s", str(e), exc_info=True)
            return []

    def _get_file_path(self, owner_id: str) -> Path:
        """获取文件路径"""
        if not self._data_dir:
            self.logger.error("数据目录未设置")
            raise RuntimeError("数据目录未设置")
        return self._data_dir / owner_id / self._segment

    @contextmanager
    def _get_file_lock(self, owner_id: str):
        """获取特定所有者的文件锁"""
        with self._file_locks_lock:
            if owner_id not in self._file_locks:
                self._file_locks[owner_id] = threading.Lock()
            file_lock = self._file_locks[owner_id]
        try:
            file_lock.acquire()
            yield
        finally:
            file_lock.release()