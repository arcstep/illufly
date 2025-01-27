from typing import Dict, List
from pydantic import Field

from .models import Fact

class FactsManager():
    """事实摘要管理器，提炼L0前检查是否需要提炼，提炼后合并到队列
    
    事实管理器，通常用于保存一个 thread_id 的所有的事实摘要。
    """
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.facts: Dict[str, List[Fact]] = {}
    
    def add_fact(self, fact: Fact):
        """添加新的事实摘要"""
        if fact.title not in self.facts:
            self.facts[fact.title] = []
        self.facts[fact.title].append(fact)
        # 按时间戳排序
        self.facts[fact.title].sort(key=lambda x: x.timestamp)
        
    def get_latest_facts(self) -> Dict[str, Fact]:
        """获取每个名称的最新事实摘要"""
        return {
            name: facts[-1] 
            for name, facts in self.facts.items()
            if facts
        }

    def merge_similar_facts(self) -> None:
        """合并相似事实，避免冗余"""
        pass
        
    def prune_outdated_facts(self) -> None:
        """清理过期事实"""
        pass
