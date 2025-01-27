from typing import Dict, List
from .models import Dialogue

class DialogueManager():
    """对话管理器，保存一个 thread_id 的所有对话"""
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.dialogues: Dict[str, List[Dialogue]] = {}
