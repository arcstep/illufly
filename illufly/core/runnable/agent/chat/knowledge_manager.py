import re
from typing import Any, Set, Union
from ....document import Document

class KnowledgeManager:
    def __init__(self, knowledge: Union[Set[str], Set[Document]] = None, **kwargs):
        """
        知识库在内存中以集合的方式保存，确保了其具有唯一性。
        """
        if isinstance(knowledge, set):
            for text in knowledge:
                if not isinstance(text, str):
                    raise ValueError("Knowledge must be a set of strings")
            self.knowledge: Set[Document] = set(Document(text) for text in knowledge)
        elif isinstance(knowledge, set):
            self.knowledge: Set[Document] = knowledge
        else:
            self.knowledge: Set[Document] = set()

    def add_knowledge(self, text: str):
        if isinstance(text, str):
            self.knowledge.add(Document(text))
        elif isinstance(text, Document):
            self.knowledge.add(text)
        else:
            raise ValueError("Knowledge must be a string or a Document")

    def get_knowledge(self, filter: str = None):
        if filter:
            return [kg.text for kg in self.knowledge if re.search(filter, kg.text)]
        else:
            return [kg.text for kg in self.knowledge]

    def clear_knowledge(self):
        self.knowledge.clear()
