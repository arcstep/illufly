from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging
from ..rocksdb import default_rocksdb, IndexedRocksDB
from .models import Thread

class ThreadManager():
    """Base Agent"""
    def __init__(
        self,
        db: IndexedRocksDB = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.db = db or default_rocksdb

        Thread.register_indexes(self.db)

    def all_threads(self, user_id: str):
        """获取所有对话"""
        threads = self.db.values(
            prefix=Thread.get_prefix(user_id)
        )
        return sorted(threads, key=lambda x: x.created_at)
    
    def new_thread(self, user_id: str):
        """创建新对话"""
        new_thread = Thread(user_id=user_id)
        self.db.update_with_indexes(
            model_name=Thread.__name__,
            key=Thread.get_key(user_id, new_thread.thread_id),
            value=new_thread
        )
        return new_thread
        
    def update_thread_title(self, user_id: str, thread_id: str, title: str):
        """更新对话标题"""
        key = Thread.get_key(user_id, thread_id)
        logging.info(f"开始更新对话标题, key: {key}, title: '{title}'")
        
        try:
            thread = self.db.get(key)
            if thread:
                logging.info(f"找到线程: {thread}")
                old_title = thread.title
                thread.title = title
                self.db.update_with_indexes(
                    model_name=Thread.__name__,
                    key=key,
                    value=thread
                )
                logging.info(f"成功更新对话标题: '{old_title}' -> '{title}'")
                return thread
            else:
                logging.warning(f"更新标题失败: 未找到线程, key={key}")
                return None
        except Exception as e:
            logging.error(f"更新标题时发生错误: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None
