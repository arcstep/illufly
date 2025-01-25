from .base import BaseContext
from typing import Dict, Any, List

class KnowledgeBaseContext(BaseContext):
    """知识库上下文
    
    从结构化知识库中检索相关信息
    """
    def __init__(self, knowledge_base, **kwargs):
        super().__init__(**kwargs)
        self.knowledge_base = knowledge_base

    def handle_input_messages(self, messages: List[Dict[str, Any]]):
        """根据用户问题检索相关知识"""
        query = messages[-1]['content']
        related_knowledge = self.knowledge_base.search(query)
        return [{'role': 'system', 'content': related_knowledge}] + messages 