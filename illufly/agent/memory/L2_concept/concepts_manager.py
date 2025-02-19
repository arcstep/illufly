from typing import Dict, List
from pydantic import Field

from .models import Concept

class ConceptsManager():
    """概念管理器，保存一个 thread_id 的所有概念"""
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.concepts: Dict[str, List[Concept]] = {}
