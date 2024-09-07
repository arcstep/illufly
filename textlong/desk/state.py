from typing import Dict, List, Any, Union
from langchain_core.documents import Document
from .markdown import Markdown
from .dataset import Dataset
import pandas as pd


class State():
    def __init__(
        self,
        markdown: str=None,
        from_outline: Dict[str, Document]=None,
        data: Dict[str, Dataset]=None,
        knowledge: List[str]=None,
        messages: []=None
    ):
        self.markdown = markdown or Markdown()
        self.from_outline = from_outline or {}
        self.data = data or {}
        self.knowledge = knowledge or []
        self.messages = messages or []
    
    @property
    def outline(self):
        return self.markdown.get_outline() if self.markdown else []

    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
