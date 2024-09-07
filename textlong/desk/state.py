from typing import Dict, List, Any, Union
from langchain_core.documents import Document
from .markdown import Markdown
import pandas as pd
class Dataset:
    def __init__(self, df: Union[pd.DataFrame]=None, desc: str=None):
        self.df = df
        self.desc = desc

class State():
    def __init__(
        self,
        markdown: str=None,
        outline: Markdown=None,
        from_outline: Dict[str, Document]=None,
        data: Dict[str, Dataset]=None,
        knowledge: List[str]=None,
        messages: []=None
    ):
        self.markdown = markdown or Markdown()
        self.outline = outline or []
        self.from_outline = from_outline or {}
        self.data = data or {}
        self.knowledge = knowledge or []
        self.messages = messages or []

    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
