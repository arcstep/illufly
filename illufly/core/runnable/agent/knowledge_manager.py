import re
from typing import Any, Set, Union, List
from ....config import get_env
from ...document import Document
from ..vectordb import VectorDB
from .retriever import Retriever

class KnowledgeManager:
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "knowledge": "待检索的资料或向量数据库"
        }

    def __init__(
        self, 
        knowledge: Union[Set[Any], List[Any]] = None,
    ):
        """
        知识库在内存中以集合的方式保存，确保唯一性。

        默认情况下，会将提供的第一个向量数据库作为默认向量库，默认向量库将自动加载 __ILLUFLY_DOCS__ 和 __ILLUFLY_CHART_LEARN__ 目录下的文档。
        除非在其他向量库中已经指定了如何加载这两个目录。
        """
        self.knowledge = knowledge

        if isinstance(knowledge, list):
            self.knowledge = set(knowledge)

        if not isinstance(self.knowledge, set):
            self.knowledge = set({self.knowledge}) if self.knowledge else set()

        self.default_vdb = None
        self._recalled_knowledge = []
        self._load_default_knowledge()

    def _load_default_knowledge(self):
        default_docs = set({
            get_env("ILLUFLY_DOCS"),
            get_env("ILLUFLY_CHART_LEARN")
        })
        for item in self.knowledge:
            if not isinstance(item, (str, Document, VectorDB, Retriever)):
                raise ValueError("Knowledge list items MUST be str, Document or VectorDB")

            if isinstance(item, VectorDB):
                if not self.default_vdb:
                    self.default_vdb = item
                if item in item.sources:
                    default_docs.remove(item)

        if self.default_vdb:
            for doc_folder in default_docs:
                self.default_vdb.load(dir=doc_folder)

    @property
    def recalled_knowledge(self):
        return self._recalled_knowledge

    def add_knowledge(self, item: Union[str, Document, VectorDB, Retriever]):
        if isinstance(item, (str, Document, VectorDB, Retriever)):
            self.knowledge.add(item)
        else:
            raise ValueError("Knowledge MUST be a string, Document or VectorDB")

    def get_knowledge(self, query: str=None, verbose: bool=False):
        knowledge = []
        self._recalled_knowledge.clear()
        for kg in self.knowledge:
            if isinstance(kg, Document):
                knowledge.append(kg.text)
                self._recalled_knowledge.append(kg)
            elif isinstance(kg, str):
                knowledge.append(kg)
                self._recalled_knowledge.append(kg)
            elif isinstance(kg, (VectorDB, Retriever)):
                docs = kg(query, verbose=verbose)
                self._recalled_knowledge.extend(docs)
                knowledge.append("\n\n".join([doc.text for doc in docs]))
            else:
                raise ValueError("Knowledge MUST be a string, Document or VectorDB")
        return knowledge
