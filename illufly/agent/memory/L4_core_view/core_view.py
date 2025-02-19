from typing import Dict, List
from pydantic import Field
from .models import CoreView

class CoreViewManager():
    """中心观点管理器，保存一个 thread_id 的所有中心观点"""
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.core_views: Dict[str, List[CoreView]] = {}
