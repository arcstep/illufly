from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging
from voidring import default_rocksdb, IndexedRocksDB
from ..mq import ServiceDealer, service_method
from .models import Thread, HistoryMessage

THREAD_MODEL = "thread"
MESSAGE_MODEL = "message"

class ThreadManagerDealer(ServiceDealer):
    """Base Agent"""
    def __init__(
        self,
        db: IndexedRocksDB = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.db = db or default_rocksdb

        self.db.register_collection(THREAD_MODEL, Thread)
        self.db.register_index(THREAD_MODEL, Thread, "user_id")

        self.db.register_collection(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(MESSAGE_MODEL, HistoryMessage, "created_at")

    @service_method(name="all_threads", description="获取所有对话")
    def all_threads(self, user_id: str):
        """获取所有对话"""
        threads = self.db.values(
            prefix=Thread.get_user_prefix(user_id)
        )
        return sorted(threads, key=lambda x: x.created_at)
    
    @service_method(name="new_thread", description="创建新对话")
    def new_thread(self, user_id: str):
        """创建新对话"""
        new_thread = Thread(user_id=user_id)
        self.db.update_with_indexes(
            collection_name=THREAD_MODEL,
            key=Thread.get_key(user_id, new_thread.thread_id),
            value=new_thread
        )
        return new_thread
    
    @service_method(name="load_messages", description="加载历史对话")
    def load_messages(self, user_id: str, thread_id: str):
        """加载历史对话"""

        return sorted(
            self.db.values(
                prefix=HistoryMessage.get_thread_prefix(user_id, thread_id)
            ),
            key=lambda x: x.completed_at
        )
