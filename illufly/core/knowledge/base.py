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

    @property
    def tags(self) -> List[str]:
        return list(self.tag_index.keys())

    def _find_duplicate(self, text: str, tags: List[str] = None) -> Union[str, None]:
        """查找重复的知识条目
        
        Args:
            text: 知识内容
            tags: 标签列表
        
        Returns:
            重复条目的ID，如果没有重复则返回None
        """
        for k, v in self.store.items():
            if v['text'] == text and set(v['meta']['tags']) == set(tags or []):
                return k
        return None

    def add(self, text: str, tags: List[str]=None, summary: str="", source: str=None) -> str:
        """添加新知识条目
        
        Args:
            text: 知识内容
            tags: 标签列表
            summary: 知识摘要（默认为 text 的前100字）
            source: 知识来源
        
        Returns:
            str: 如果是新增则返回新的knowledge_id，如果是重复则返回已存在的knowledge_id
        """
        # 检查重复
        duplicate_id = self._find_duplicate(text, tags)
        if duplicate_id:
            return duplicate_id
        
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
        
        # 如果要更新文本和标签，检查是否与其他条目重复
        if text is not None and tags is not None:
            duplicate_id = self._find_duplicate(text, tags)
            if duplicate_id and duplicate_id != knowledge_id:
                return False
        # 如果只更新文本，检查文本和现有标签是否与其他条目重复
        elif text is not None:
            duplicate_id = self._find_duplicate(text, self.store[knowledge_id]['meta']['tags'])
            if duplicate_id and duplicate_id != knowledge_id:
                return False
        # 如果只更新标签，检查现有文本和新标签是否与其他条目重复
        elif tags is not None:
            duplicate_id = self._find_duplicate(self.store[knowledge_id]['text'], tags)
            if duplicate_id and duplicate_id != knowledge_id:
                return False

        doc_dict = self.store[knowledge_id]

        if text is not None:
            doc_dict['text'] = text

        if tags is not None:
            doc_dict['meta']['tags'] = tags
            self._update_tag_index(knowledge_id, tags)

        if not summary and text is not None:
            summary = text[:100] + "..." if len(text) > 100 else text
        if summary:
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

    def all(self) -> List[Document]:
        """列出所有知识条目"""
        return [
            Document(text=v['text'], meta=v['meta'])
            for v in self.store.values()
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

    def get_meta_list(
        self,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "id",
        reverse: bool = False,
        tags: List[str] = None,
        match_all_tags: bool = True
    ) -> Dict[str, Union[List[Dict], int]]:
        """获取所有知识条目的元数据，支持分页和标签筛选
        
        Args:
            page: 页码（从1开始）
            page_size: 每页条数
            sort_by: 排序字段（'id', 'summary', 'source'）
            reverse: 是否倒序
            tags: 标签筛选列表
            match_all_tags: True表示必须匹配所有标签，False表示匹配任意标签
        
        Returns:
            Dict: {
                'total': 总条数,
                'total_pages': 总页数,
                'current_page': 当前页码,
                'items': [
                    {
                        'id': 知识条目ID,
                        'summary': 摘要,
                        'tags': 标签列表,
                        'source': 来源
                    },
                    ...
                ]
            }
        """
        # 如果指定了标签，先通过标签索引筛选知识条目ID
        if tags:
            knowledge_ids = set(self.find_by_tags(tags, match_all_tags))
            items = {k: v for k, v in self.store.items() if k in knowledge_ids}
        else:
            items = self.store
        
        # 获取符合条件的知识条目的元数据
        meta_list = [
            {
                'id': k,
                'summary': v['meta']['summary'],
                'tags': v['meta']['tags'],
                'source': v['meta']['source']
            }
            for k, v in items.items()
        ]
        
        # 排序
        if sort_by == 'id':
            meta_list.sort(key=lambda x: x['id'], reverse=reverse)
        elif sort_by in ['summary', 'source']:
            meta_list.sort(key=lambda x: (x[sort_by] or '').lower(), reverse=reverse)
        elif sort_by == 'tags':
            # 按标签数量和第一个标签的字母顺序排序
            meta_list.sort(key=lambda x: (len(x['tags']), x['tags'][0] if x['tags'] else ''), 
                          reverse=reverse)
        
        # 计算分页信息
        total = len(meta_list)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        page = min(max(1, page), total_pages)
        
        # 切片获取当前页的数据
        start = (page - 1) * page_size
        end = start + page_size
        page_items = meta_list[start:end]
        
        return {
            'total': total,
            'total_pages': total_pages,
            'current_page': page,
            'items': page_items,
            'filters': {
                'tags': tags or [],
                'match_all_tags': match_all_tags
            }
        }

