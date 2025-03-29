from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging
from ..rocksdb import default_rocksdb, IndexedRocksDB
from .models import Thread, ChunkType, DialougeChunk

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
        DialougeChunk.register_indexes(self.db)

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
