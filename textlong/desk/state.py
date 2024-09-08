from typing import Dict, List, Any, Union, Set
from langchain_core.documents import Document
import pandas as pd
import re
import copy

from ..utils import compress_text
from .markdown import Markdown

class Dataset:
    def __init__(self, df: Union[pd.DataFrame]=None, desc: str=None):
        self.df = df
        self.desc = desc
    
    def __str__(self):
        return self.desc

    def __repr__(self):
        return f"Dataset(desc={self.desc})"

class Knowledge:
    def __init__(self, text: str):
        self.text = text

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"Knowledge(text={self.text})"

class State():
    def __init__(
        self,
        markdown: str=None,
        from_outline: Dict[str, Document]=None,
        data: Dict[str, Dataset]=None,
        knowledge: Set[str]=None,
        messages: []=None
    ):
        """    
        Args:
        - markdown: 当前的 Markdown 对象，在执行 from_outline 后，并不会修改这个对象
        - messages: 当前对话产生的消息列表，但不包括扩写提纲产生的部份（那应当在 from_outline 中）
        - from_outline: 从 Markdown 中解析出的提纲进行扩写，结果应当是字典，Key 是提纲 Document 的 id，Value 是扩写时的消息列表
        - data: 在对话过程中（包括扩写），根据推理要求触发数据分析回调工具去读写数据集的内容
        - knowledge: 在对话过程中（包括扩写），根据需要加载的知识
        """
        self.markdown = markdown or Markdown()
        self.from_outline = from_outline or {}
        self.data = data or {}
        self.knowledge = knowledge or []
        self.messages = messages or []
    
    def __str__(self):
        return f"State(output={compress_text(self.output) or None}, data={','.join(self.get_dataset_names()) or None})"

    def __repr__(self):
        return f"State(output={compress_text(self.output) or None}, data={','.join(self.get_dataset_names()) or None})"
    
    @property
    def output(self):
        """
        从 Markdown 生成当前的文本输出内容。
        如果当前有提纲，则将提纲中的内容替换为实际内容。
        """
        if self.outline:
            md = copy.deepcopy(self.markdown)
            for doc in self.outline:
                if doc.metadata['id'] in self.from_outline:
                    from_outline_text = self.rom_outline[doc.metadata['id']][-1]['content']
                    md.replace_documents(doc, doc, from_outline_text)
            return md.text
        else:
            return self.markdown.text
    
    @property
    def outline(self):
        """
        获取当前的 Markdown 中包含的提纲，返回一个 Document 列表
        """
        return self.markdown.get_outline() if self.markdown else []

    # 管理数据集
    def add_dataset(self, name: str, df: pd.DataFrame, desc: str=None):
        self.data[name] = Dataset(df, desc or name)

    def get_dataset(self, name: str):
        return self.data.get(name)
    
    def get_dataset_names(self):
        return list(self.data.keys())
    
    def clear_dataset(self):
        self.data.clear()

    # 管理知识
    def add_knowledge(self, text: str):
        self.knowledge.add(text)

    def get_knowledge(self, filter: str=None):
        if filter:
            return [k for k in self.knowledge if re.search(filter, k)]
        else:
            return list(self.knowledge)

    def clear_knowledge(self):
        self.knowledge.clear()
