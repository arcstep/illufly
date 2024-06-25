import re
import copy
import os
import yaml
from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from ..parser import parse_markdown, create_front_matter

class MarkdownLoader(BaseLoader):
    def __init__(self, doc_str: str=None):
        self.documents = []
        self.import_markdown(doc_str)

    def lazy_load(self) -> Iterator[Document]:
        for doc in self.documents:
            yield doc

    def load(self) -> List[Document]:
        return list(self.lazy_load())

    def import_markdown(self, doc_str: str=None):
        """
        导入Markdown文档。
        """
        filename = doc_str
        if filename and os.path.isfile(filename) and os.path.exists(doc_str):
            if filename.endswith(".md") or filename.endswith(".MD"):
                md_file = filename

                with open(md_file, 'r') as file:
                    doc_str = file.read()

        if doc_str:
            self.documents = parse_markdown(doc_str)

        return self.documents

    @classmethod
    def to_markdown(cls, documents: List[Document], sep: str="", with_front_matter: bool=False):
        if not documents:
            return ''

        meta0 = documents[0].metadata
        front_matter = ''
        if with_front_matter and 'type' in meta0 and meta0['type'] == 'front_matter':
            front_matter = create_front_matter(meta0)

        return front_matter + sep.join([d.page_content for d in documents])

    @property
    def markdown(self):
        return self.__class__.to_markdown(self.documents)
    
    @property
    def types(self):
        s = set()
        for d in self.documents:
            s.add(d.metadata['type'])
        print(s)

    def get_todo_documents(self, sep_mode: Union[str, List[str]]="all", pattern: str=None, score: float=None, k: int=None):
        """
        将文档拆分为N个批次, 构建任务清单。

        Args:
        - sep_mode: 拆分模式
            # 整体返回, 返回 ('all', List[doc: Document])
            - 'all', 获得全部文档

            # 从Document类型拆分, 返回 ('document', List[index: int])
            - 'document', 逐个文档元素
            - 'outline', 仅<OUTLINE><OUTLINE/>中的部份

            # 从Document类型拆分, 返回 ('document', List[(from: int, to: int)])
            - 'section', 将所有相邻的非标题内容连成一个批次并包括上文紧邻的标题
            - 'not-heading', 将所有非标题内容连成一个批次
            - 'headings', 将所有标题内容连成一个批次
            - {元素名称}, 按标题、代码块、列表、paragraph等元素

            # 从文本拆分, 返回 ('md', List[(from: int, to: int)])
            - 'chunk', 合并Document, 直到合并后的内容超过字数限制k
            - 'paragraph', 按每一个换行符

        - pattern: 按正则表达式匹配并过滤
        - score: 按向量相似性分数过滤

        - k: 如果长度不超过k就合并批次

        Return: 拆分好的文档和插入位置的元组。
        - ('all', List[doc: Document])
        - ('document', List[index: int])
        - ('document', List[(from: int, to: int)])
        - ('md', List[(from: int, to: int)])
        """
        sep_mode = sep_mode.lower()
        pattern = pattern or '.*'

        if sep_mode == 'all':
            docs = [
                d
                for d in self.documents
                if re.search(pattern, d.page_content)
            ]
            return ('all', docs)

        elif sep_mode == 'element':
            docs = [
                (d, i)
                for i, d in enumerate(self.documents) 
                if re.search(pattern, d.page_content)
            ]
            return ('document', docs)

        elif sep_mode in ['heading', 'list', 'block_code', 'paragraph']:
            docs = [
                (d, i)
                for i, d in enumerate(self.documents) 
                if re.search(pattern, d.page_content)
                and d.metadata['type'] in sep_mode
            ]
            return ('document', docs)

        elif sep_mode == 'outline':
            docs = [
                (d, i)
                for i, d in enumerate(self.documents) 
                if d.metadata['type'] == "OUTLINE"
                and re.search(pattern, d.page_content)
            ]
            return ('document', docs)

        elif sep_mode == 'segment':
            docs = [
                (d, i)
                for i, d in enumerate(self.documents) 
                if re.search(pattern, d.page_content)
                and d.metadata['type'] != 'heading'
            ]
            segments = []
            if docs:
                chunk = [docs[0]]
                for i in range(1, len(docs)):
                    if docs[i][1] == chunk[-1][1] + 1:
                        chunk.append(docs[i])
                    else:
                        segments.append([d for d, i in chunk])
                        chunk = [docs[i]]
                segments.append([d for d, i in chunk])
            return ('segment', segments)

        return ('unknown', [])

    def get_task_range(self, index_from: Union[str, Document], index_to: Union[str, Document]):
        """
        获得任务索引。
        """
        index_from = index_from.metadata['id'] if isinstance(index_from, Document) else index_from
        index_to = index_to.metadata['id'] if isinstance(index_to, Document) else index_to
        _from = None
        _to = None
        for i, doc in enumerate(self.documents):
            if doc.metadata['id'] == index_from:
                _from = i
            if doc.metadata['id'] == index_to:
                _to = i
            if _from != None and _to != None:
                return (_from, _to)
        return (_from, _to)

    def replace_documents(self, index_from: Union[str, Document], index_to: Union[str, Document], docs: Union[str, List[Document]]=None):
        """
        替换文档对象。
        """
        to_insert = parse_markdown(docs) if isinstance(docs, str) else docs

        _from, _to = self.get_task_range(index_from, index_to)
        if _from == None:
            raise ValueError(f"{index_from} NOT FOUND!")
        if _to == None:
            raise ValueError(f"{index_to} NOT FOUND!")

        self.documents = self.documents[:_from] + to_insert + self.documents[_to + 1:]
        return self.documents

    def get_prev_documents(self, index_doc: Union[int, str, Document]=None, k: int=800):
        """
        获得向前关联文档。
        """
        if index_doc is None:
            return []

        task_id = index_doc.metadata['id'] if isinstance(index_doc, Document) else index_doc

        md = ""
        found_task = False
        last_header_level = None
        docs = []

        for doc in self.documents[::-1]:
            if not found_task:
                if doc.metadata['id'] == task_id:
                    found_task = True
                continue

            # 在token数量可承受范围内优先前文
            md = doc.page_content + md
            if len(md) <= k:
                docs.append(doc)
                continue

            # 补充所有祖先标题
            doc_is_header = doc.metadata['type'] == "heading"
            if doc_is_header:
                doc_level = doc.metadata['attrs']['level']
                if last_header_level == None or doc_level <= last_header_level:
                    docs.append(doc)
                    last_header_level = doc_level

        return docs[::-1]

    def get_next_documents(self, index_doc: Union[str, Document]=None, k:int =200):
        """
        获得向后关联文档。
        """
        if index_doc is None:
            return []

        task_id = index_doc.metadata['id'] if isinstance(index_doc, Document) else index_doc

        md = ""
        found_task = False
        docs = []

        for doc in self.documents:
            if not found_task:
                if doc.metadata['id'] == task_id:
                    found_task = True
                continue

            md = doc.page_content + md
            if len(md) <= k:
                docs.append(doc)
            else:
                break

        return docs