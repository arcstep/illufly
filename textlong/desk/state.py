from typing import Dict, List, Any
from langchain_core.documents import Document
from .markdown import Markdown

class State():
    def __init__(
        self,
        markdown: str=None,
        outline: Markdown=None,
        from_outline: Dict[str, Document]=None,
        data: Dict[str, Any]=None,
        knowledge: List[str]=None,
        messages: []=None
    ):
        self.markdown = markdown or Markdown()
        self.outline = outline or []
        self.from_outline = from_outline or {}
        self.data = data or {}
        self.knowledge = knowledge or []
        self.messages = messages or []
