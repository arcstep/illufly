from typing import Dict, List, Any
from langchain_core.documents import Document
from .markdown import Markdown

class State():
    def __init__(
        self,
        output: str=None,
        outline: Markdown=None,
        from_outline: Dict[str, Document]=None,
        data: Dict[str, Any]=None,
        knowledge: List[str]=None,
        messages: []=None
    ):
        self.output = output or ''
        self.outline = outline or Markdown()
        self.from_outline = from_outline or {}
        self.data = data or {}
        self.knowledge = knowledge or []
        self.messages = messages or []
