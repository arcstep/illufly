from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

import uuid
import logging
from ..rocksdb import default_rocksdb, IndexedRocksDB
from ..mq import ServiceDealer, service_method
from .models import Thread, HistoryMessage

THREAD_MODEL = "thread"
MESSAGE_MODEL = "message"

class ThreadManager(ServiceDealer):
    """Base Agent"""
    def __init__(
        self,
        db: IndexedRocksDB = None,
        **kwargs
    ):
        self.db = db or default_rocksdb

        self.db.register_model(THREAD_MODEL, Thread)
        self.db.register_model(MESSAGE_MODEL, HistoryMessage)
        self.db.register_index(THREAD_MODEL, "user_id")

    @service_method(name="all_threads", description="获取所有对话")
    def all_threads(self, user_id: str):
        return self.db.values(
            prefix=Thread.get_user_prefix(user_id)
        )
    
    @service_method(name="new_thread", description="创建新对话")
    def new_thread(self, user_id: str):
        """创建新对话"""
        new_thread = Thread(user_id=user_id)
        self.db.update_with_indexes(
            model_name=THREAD_MODEL,
            key=new_thread.get_key(),
            value=new_thread
        )
        return new_thread
    
    @service_method(name="load_messages", description="加载历史对话")
    def load_messages(self, user_id: str, thread_id: str):
        """加载历史对话"""
        return self.db.values(
            prefix=HistoryMessage.get_thread_prefix(user_id, thread_id)
        )
