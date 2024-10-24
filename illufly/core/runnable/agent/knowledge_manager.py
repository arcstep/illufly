import re
from typing import Any, Set, Union, List
from ....config import get_env
from ...document import Document
from ..vectordb import VectorDB
from .retriever import Retriever

class KnowledgeManager:
    @classmethod
    def available_init_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "knowledge": "待检索的资料",
            "faq": "待检索的常识",
            "embeddings": "用于文本嵌入的向量模型, 如果提供就使用它构建默认的检索器、向量库"
        }

    def __init__(
        self, 
        knowledge: Union[Set[Any], List[Any]] = None,
        faq: Union[Set[Any], List[Any]] = None,
    ):
        """
        知识库在内存中以集合的方式保存，确保唯一性。
        """
        self.knowledge = knowledge
        self.faq = faq

        if isinstance(knowledge, list):
            self.knowledge = set(knowledge)
        if isinstance(faq, list):
            self.faq = set(faq)

        if not isinstance(self.knowledge, set):
            self.knowledge = set({self.knowledge}) if self.knowledge else set()
        if not isinstance(self.faq, set):
            self.faq = set({self.faq}) if self.faq else set()

        for item in self.knowledge:
            if not isinstance(item, (str, Document, VectorDB, Retriever)):
                raise ValueError("Knowledge list items MUST be str, Document or VectorDB")

            if isinstance(item, VectorDB):
                if not item.top_k:
                    item.top_k = 5
                if not item.documents:
                    item.load(dir=get_env("ILLUFLY_DOCS"))

        for item in self.faq:
            if not isinstance(item, (str, Document, VectorDB, Retriever)):
                raise ValueError("Task-Final-Answer MUST be str, Document or VectorDB")

            if isinstance(item, VectorDB):
                if not item.top_k:
                    item.top_k = 1
                if not item.documents:
                    item.load(dir=get_env("ILLUFLY_FAQ"))

    def add_knowledge(self, item: Union[str, Document, VectorDB, Retriever]):
        if isinstance(item, (str, Document, VectorDB, Retriever)):
            self.knowledge.add(item)
        else:
            raise ValueError("Knowledge MUST be a string, Document or VectorDB")

    def add_faq(self, item: Union[str, Document, VectorDB, Retriever]):
        if isinstance(item, (str, Document, VectorDB)):
            self.faq.add(item)
        else:
            raise ValueError("Task-Final-Answer MUST be a string, Document or VectorDB")

    def get_knowledge(self, query: str=None, verbose: bool=False):
        knowledge = []
        for kg in self.knowledge:
            if isinstance(kg, Document):
                knowledge.append(kg.text)
            elif isinstance(kg, str):
                knowledge.append(kg)
            elif isinstance(kg, (VectorDB, Retriever)):
                query_results = [doc.text for doc in kg(query, verbose=verbose)]
                knowledge.append("\n\n".join(query_results))
            else:
                raise ValueError("Knowledge MUST be a string, Document or VectorDB")
        return knowledge

    def get_faq(self, query: str=None, verbose: bool=False):
        knowledge = []
        for kg in self.faq:
            if isinstance(kg, Document):
                knowledge.append(kg.text)
            elif isinstance(kg, str):
                knowledge.append(kg)
            elif isinstance(kg, (VectorDB, Retriever)):
                query_results = [doc.text for doc in kg(query, verbose=verbose)]
                knowledge.append("\n\n".join(query_results))
            else:
                raise ValueError("Task-Final-Answer MUST be a string, Document or VectorDB")
        return knowledge

    def clear_knowledge(self):
        self.knowledge.clear()

    def clear_faq(self):
        self.faq.clear()
