import re
from typing import List, Any, Set

class Knowledge:
    def __init__(self, text: str):
        self.text = text

    def __str__(self):
        return self.text

    def __repr__(self):
        return f"Knowledge(text={self.text})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Knowledge) and self.text == other.text

    def __hash__(self) -> int:
        return hash(self.text)


class KnowledgeManager:
    def __init__(self, knowledge: List[str] = None):
        self.knowledge: Set[Knowledge] = set(Knowledge(text) for text in knowledge) if knowledge else set()
    
    def add_knowledge(self, text: str):
        self.knowledge.add(Knowledge(text))

    def append_knowledge_to_messages(self, new_memory: List[Any]):
        existing_contents = {msg['content'] for msg in new_memory if msg['role'] == 'user'}
        for kg in self.get_knowledge():
            content = f'已知：{kg}'
            if content not in existing_contents:
                new_memory.extend([{
                    'role': 'user',
                    'content': content
                },
                {
                    'role': 'assistant',
                    'content': 'OK, 我将利用这个知识回答后面问题。'
                }])
        return new_memory

    def get_knowledge(self, filter: str = None):
        if filter:
            return [kg.text for kg in self.knowledge if re.search(filter, kg.text)]
        else:
            return [kg.text for kg in self.knowledge]

    def clear_knowledge(self):
        self.knowledge.clear()
