import re
from typing import Any, Set, Union, List
from ....document import Document
from ...vectordb import VectorDB

class KnowledgeManager:
    def __init__(self, knowledge: Union[Set[Any], List[Any]] = None, **kwargs):
        """
        知识库在内存中以集合的方式保存，确保了其具有唯一性。
        """
        if isinstance(knowledge, set):
            for text in knowledge:
                if not isinstance(item, (str, Document, VectorDB)):
                    raise ValueError("Knowledge list items must be str, Document, or VectorDB")
            self.knowledge = knowledge
        else:
            self.knowledge = set(knowledge or {})

    def add_knowledge(self, text: str):
        if isinstance(text, str):
            self.knowledge.add(Document(text))
        elif isinstance(text, Document):
            self.knowledge.add(text)
        else:
            raise ValueError("Knowledge must be a string or a Document")

    def get_knowledge(self, query: str=None):
        knowledge = []
        for kg in self.knowledge:
            if isinstance(kg, Document):
                knowledge.append(kg.text)
            elif isinstance(kg, str):
                knowledge.append(kg)
            elif isinstance(kg, VectorDB):
                query_results = [doc.text for (score, doc) in kg(query, verbose=self.verbose)]
                knowledge.append("\n\n".join(query_results))
            else:
                raise ValueError("Knowledge must be a string, Document or VectorDB")
        return knowledge

    def clear_knowledge(self):
        self.knowledge.clear()
