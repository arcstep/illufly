from typing import List, Union, Dict, Set
from dataclasses import dataclass
from pathlib import Path
import copy
import json
from ...utils import create_id_generator
from ..document import Document

knowledge_id_gen = create_id_generator()

class BaseKnowledge():
    def __init__(self, store: dict=None):
        self.store = store if store is not None else {}
        self.id_gen = knowledge_id_gen
        self.tag_index: Dict[str, Set[str]] = {}  # 标签索引: {tag: set(knowledge_ids)}

    def add(self, text: str, tags: List[str]=None, summary: str="", source: str=None) -> str:
        """添加新知识条目
        
        Args:
            text: 知识内容
            tags: 标签列表
            summary: 知识摘要（默认为 text 的前100字）
            source: 知识来源
        """
        if not summary:
            summary = text[:100] + "..." if len(text) > 100 else text
        
        knowledge_id = next(self.id_gen)
        doc = Document(
            text=text,
            meta={
                'tags': tags or [],
                'summary': summary,
                'source': source,
                'id': knowledge_id
            }
        )
        
        self.store[knowledge_id] = copy.deepcopy(doc.to_dict())
        self._update_tag_index(knowledge_id, doc.meta['tags'])
        return knowledge_id

    def get(self, knowledge_id: str) -> Union[Document, None]:
        """获取指定知识条目"""
        return self.store.get(knowledge_id, None)

    def update(
        self, 
        knowledge_id: str, 
        text: str=None, 
        tags: List[str]=None, 
        summary: str=None, 
        source: str=None
    ) -> bool:
        """更新指定知识条目"""
        if knowledge_id not in self.store:
            return False

        doc_dict = self.store[knowledge_id]

        if text is not None:
            doc_dict['text'] = text

        if tags is not None:
            doc_dict['meta']['tags'] = tags
            self._update_tag_index(knowledge_id, tags)

        if not summary:
            summary = text[:100] + "..." if len(text) > 100 else text
        doc_dict['meta']['summary'] = summary

        if source is not None:
            doc_dict['meta']['source'] = source

        return True

    def _update_tag_index(self, knowledge_id: str, tags: List[str]) -> None:
        """更新标签索引"""
        # 清理旧标签
        for tag in self.tag_index:
            self.tag_index[tag].discard(knowledge_id)
        
        # 添加新标签
        for tag in tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = set()
            self.tag_index[tag].add(knowledge_id)

    def delete(self, knowledge_id: str) -> bool:
        """删除指定知识条目"""
        if knowledge_id in self.store:
            doc = self.get(knowledge_id)
            self._update_tag_index(knowledge_id, [])
            del self.store[knowledge_id]
            return True
        return False

    def all(self) -> List[Dict[str, Union[str, Document]]]:
        """列出所有知识条目"""
        return [
            {
                "id": k,
                "data": Document(**copy.deepcopy(v))
            } 
            for k, v in self.store.items()
        ]

    def find_by_tags(self, tags: List[str], match_all: bool=True) -> List[str]:
        """根据标签查找知识条目ID

        Args:
            tags: 标签列表
            match_all: True表示必须匹配所有标签，False表示匹配任意标签
        """
        if not tags:
            return []
            
        result = set(self.tag_index.get(tags[0], set()))
        if match_all:
            for tag in tags[1:]:
                result &= self.tag_index.get(tag, set())
        else:
            for tag in tags[1:]:
                result |= self.tag_index.get(tag, set())
                
        return list(result)

