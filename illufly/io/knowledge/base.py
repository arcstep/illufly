from typing import List, Union, Dict, Set
from dataclasses import dataclass
from pathlib import Path
import copy
import json
from ...utils import create_id_generator
import os
import fnmatch
from .markmeta import MarkMeta
from ..document import Document

knowledge_id_gen = create_id_generator()

class BaseKnowledge():
    def __init__(self, store: dict=None, chunk_size: int=1024, chunk_overlap: int=100):
        self.store = store if store is not None else {}
        self.id_gen = knowledge_id_gen
        self.tag_index: Dict[str, Set[str]] = {}  # 标签索引: {tag: set(knowledge_ids)}
        
        # 文本分块参数
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._parser = MarkMeta(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

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
        """添加新知识条目，自动处理大文本分块
        
        Args:
            text: 知识内容
            tags: 标签列表
            summary: 知识摘要（默认为 text 的前100字）
            source: 知识来源
        
        Returns:
            str: 如果是新增则返回新的knowledge_id列表，如果是重复则返回已存在的knowledge_id
        """
        # 确保 source 是字符串
        source = str(source) if source is not None else ""
        
        # 检查重复
        duplicate_id = self._find_duplicate(text, tags)
        if duplicate_id:
            return duplicate_id

        if not summary:
            summary = text[:100] + "..." if len(text) > 100 else text
            
        # 使用 MarkMeta 解析和分块
        docs = self._parser.parse_text(text, source=source)
        
        # 如果只有一个文档，直接添加
        if len(docs) == 1:
            doc = docs[0]
            doc.meta.update({
                'tags': tags or [],
                'summary': summary,
                'source': source,
                'id': next(self.id_gen)
            })
            
            self.store[doc.meta['id']] = copy.deepcopy(doc.to_dict())
            self._update_tag_index(doc.meta['id'], doc.meta['tags'])
            return doc.meta['id']
            
        # 如果有多个分块，为每个分块创建条目
        knowledge_ids = []
        for i, doc in enumerate(docs):
            chunk_id = next(self.id_gen)
            doc.meta.update({
                'tags': tags or [],
                'summary': f"{summary} (分块 {i+1}/{len(docs)})",
                'source': source,
                'id': chunk_id,
                'is_chunk': True,
                'chunk_index': i,
                'total_chunks': len(docs)
            })
            
            self.store[chunk_id] = copy.deepcopy(doc.to_dict())
            self._update_tag_index(chunk_id, doc.meta['tags'])
            knowledge_ids.append(chunk_id)
            
        return knowledge_ids[0] if knowledge_ids else None

    def get(self, knowledge_id: str) -> Union[Document, None]:
        """获取指定知识条目
        
        Args:
            knowledge_id: 知识条目ID
        Returns:
            Document: 文档对象，如果不存在则返回None
        """
        doc_dict = self.store.get(knowledge_id)
        if doc_dict is None:
            return None
        return Document(
            text=doc_dict['text'],
            meta=doc_dict['meta']
        )

    def update(
        self, 
        knowledge_id: str, 
        text: str=None, 
        tags: List[str]=None, 
        summary: str=None, 
        source: str=None
    ) -> Union[Document, bool]:
        """更新指定知识条目
        
        Args:
            knowledge_id: 知识条目ID
            text: 新的文档文本
            tags: 新的标签列表
            summary: 新的摘要
            source: 新的来源
        Returns:
            Union[Document, bool]: 更新成功返回更新后的Document对象，失败返回False
        """
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

        return Document(text=doc_dict['text'], meta=doc_dict['meta'])

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
        """删除指定知识条目
        
        Args:
            knowledge_id: 要删除的知识条目ID
        Returns:
            bool: 删除是否成功
        """
        if knowledge_id in self.store:
            # 先获取文档以便清理标签
            doc = self.get(knowledge_id)
            if doc and doc.meta.get('tags'):
                self._update_tag_index(knowledge_id, [])
            del self.store[knowledge_id]
            return True
        return False

    def all(self) -> List[Document]:
        """列出所有知识条目
        
        Returns:
            List[Document]: 所有文档对象列表
        """
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
            meta_list.sort(
                key=lambda x: (len(x['tags']), x['tags'][0] if x['tags'] else ''), 
                reverse=reverse
            )
        
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

    def import_files(self, dir_path: str, filter: str = "*", exts: List[str] = None, tags: List[str] = None) -> List[str]:
        """从目录导入知识
        
        Args:
            dir_path: 目录路径
            filter: 文件名过滤器
            exts: 文件扩展名列表，默认为 ['.md', '.Md', '.MD', '.markdown', '.MARKDOWN']
            tags: 要添加的标签列表，默认为 ['imported_files']
            
        Returns:
            List[str]: 导入的知识条目ID列表（已去重）
        """        
        exts = exts or ['.md', '.Md', '.MD', '.markdown', '.MARKDOWN']
        imported_ids = set()  # 使用集合来自动去重
        
        # 设置默认标签
        default_tags = tags if tags is not None else ['imported_files']
        
        # 遍历目录获取文件
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.startswith('.'):  # 跳过隐藏文件
                    continue
                if not any(file.endswith(ext) for ext in exts):
                    continue
                if not fnmatch.fnmatch(file, filter):
                    continue
                    
                file_path = os.path.join(root, file)
                imported_ids.update(self.import_file(file_path, tags=default_tags))
                
        return list(imported_ids)

    def import_file(self, file_path: str, tags: List[str] = None) -> List[str]:
        """导入单个文件
        
        Args:
            file_path: 文件路径
            tags: 默认标签列表，如果未指定则使用 ['imported_files']
            
        Returns:
            List[str]: 导入的知识条目ID列表（已去重）
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 设置默认标签
        default_tags = tags if tags is not None else ['imported_files']
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return []
        
        # 使用 MarkMeta 解析文档
        docs = self._parser.parse_text(content, source=file_path)
        
        # 导入解析后的文档
        imported_ids = set()
        for doc in docs:
            # 合并文档自带的标签和默认标签
            tags = list(set(doc.meta.get('tags', []) + default_tags))
            
            # 检查是否存在重复内容
            duplicate_id = self._find_duplicate(doc.text, tags)
            if duplicate_id:
                # 更新已存在的条目
                self.update(
                    knowledge_id=duplicate_id,
                    text=doc.text,
                    tags=tags,
                    summary=doc.meta.get('summary', ''),
                    source=doc.meta.get('source', file_path)
                )
                imported_ids.add(duplicate_id)
                continue
            
            # 添加新条目
            knowledge_id = self.add(
                text=doc.text,
                tags=tags,
                summary=doc.meta.get('summary', ''),
                source=doc.meta.get('source', file_path)
            )
            if isinstance(knowledge_id, list):
                imported_ids.update(knowledge_id)
            else:
                imported_ids.add(knowledge_id)
                
        return list(imported_ids)

