from typing import Dict, List
from pydantic import Field

from .models import ThematicGraph

class ThematicGraphManager():
    """主题图管理器，保存一个 thread_id 的所有主题图"""
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.thematic_graphs: Dict[str, List[ThematicGraph]] = {}
