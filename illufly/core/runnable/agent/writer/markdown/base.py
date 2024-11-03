import re
import copy
import os
import yaml
from typing import Iterator, List, Union, Optional

from ......config import get_env
from ......utils import extract_text
from .....document import Document
from .utils import parse_markdown, create_front_matter

class Markdown():
    def __init__(self, doc_str: str=None, md_file: str=None, source: str=None):
        self.documents = []
        self.doc_str = doc_str
        self.md_file = md_file
        self.source = source or md_file
        self.import_markdown(doc_str, md_file)

    def import_markdown(self, doc_str: str=None, md_file: str=None):
        """
        导入Markdown文档。
        """
        _doc_str = doc_str or self.doc_str
        _md_file = md_file or self.md_file
        if _md_file and os.path.isfile(_md_file) and os.path.exists(_md_file):
            with open(_md_file, 'r', encoding='utf-8') as file:
                _doc_str = file.read()

        if _doc_str:
            self.documents = parse_markdown(_doc_str, source=self.source)

        return self.documents
    
    @classmethod
    def to_text(cls, documents: List[Document], sep: str="", with_front_matter: bool=False):
        if not documents:
            return ''

        meta0 = documents[0].meta
        front_matter = ''
        if with_front_matter and 'type' in meta0 and meta0['type'] == 'front_matter':
            front_matter = create_front_matter(meta0)

        return front_matter + sep.join([d.text for d in documents])

    @property
    def text(self):
        return self.__class__.to_text(self.documents)

    def get_all(self, pattern: str=None):
        return [
            d
            for d in self.documents
            if re.search(pattern or '.*', d.text)
        ]

    def get_outline(self, pattern: str=None):
        return [
            d
            for d in self.documents
            if d.meta['type'] == "OUTLINE"
            and re.search(pattern or '.*', d.text)
        ]
    
    def fetch_outline_task(self, outline_doc: Document, prev_k: int=800, next_k: int=200):
        """
        提取提纲内容。

        返回结果为 (draft: str, task: str)，其中：
        - draft 为结合了前后文和扩写位置说明的草稿
        - task 为具体的要求
        """
        if outline_doc.meta['type'] != 'OUTLINE':
            raise  ValueError(f"Document's type Must be OUTLINE!")

        # 提取草稿
        docs = []

        docs.extend(self.get_prev_documents(outline_doc, k=prev_k))

        outline = Document(text="<<<YOUR_TEXT>>>\n\n", meta={"type": "paragraph"})
        docs.append(outline)

        docs.extend(self.get_next_documents(outline_doc, k=next_k))

        draft = self.__class__.to_text(docs)

        # 提取任务
        tag_start = get_env("ILLUFLY_OUTLINE_START")
        tag_end = get_env("ILLUFLY_OUTLINE_END")
        md = self.__class__.to_text([outline_doc])
        task = extract_text(md, tag_start, tag_end)

        return (draft, task)

    def get_task_range(self, index_from: Union[str, Document], index_to: Union[str, Document]):
        """
        获得任务索引。
        """
        index_from = index_from.meta['id'] if isinstance(index_from, Document) else index_from
        index_to = index_to.meta['id'] if isinstance(index_to, Document) else index_to
        _from = None
        _to = None
        for i, doc in enumerate(self.documents):
            if doc.meta['id'] == index_from:
                _from = i
            if doc.meta['id'] == index_to:
                _to = i
            if _from != None and _to != None:
                return (_from, _to)
        return (_from, _to)

    def replace_documents(self, doc_from: Union[str, Document], doc_to: Union[str, Document], docs: Union[str, List[Document]]=None):
        """
        替换文档对象。
        
        如果被提取的文本与原有上文和下文重叠，就剔除重叠的部份。
        """
        to_insert = parse_markdown(docs) if isinstance(docs, str) else docs

        _from, _to = self.get_task_range(doc_from, doc_to)
        if _from == None:
            raise ValueError(f"{doc_from} NOT FOUND!")
        if _to == None:
            raise ValueError(f"{doc_to} NOT FOUND!")
        
        prev_docs = self.documents[:_from]
        next_docs = self.documents[_to + 1:]
        
        prev_heading = next((doc for doc in reversed(prev_docs) if 'type' in doc.meta and doc.meta['type'] == 'heading'), None)
        next_heading = next((doc for doc in next_docs if 'type' in doc.meta and doc.meta['type'] == 'heading'), None)

        from_index = None
        if prev_heading:
            for i, d in enumerate(to_insert):
                if d.text.strip() == prev_heading.text.strip():
                    from_index = i + 1
                    break

        to_index = None
        if next_heading:
            for i, d in enumerate(reversed(to_insert)):
                if d.text.strip() == next_heading.text.strip():
                    to_index = i
                    break

        to_insert_docs = to_insert[from_index:to_index]

        self.documents = prev_docs + to_insert_docs + next_docs
        return to_insert_docs

    def get_prev_documents(self, index_doc: Union[int, str, Document]=None, k: int=800):
        """
        获得向前关联文档。
        """
        if index_doc is None:
            return []

        task_id = index_doc.meta['id'] if isinstance(index_doc, Document) else index_doc

        md = ""
        found_task = False
        last_header_level = None
        docs = []

        for _doc in self.documents[::-1]:
            new_doc = copy.deepcopy(_doc)
            if not found_task:
                if new_doc.meta['id'] == task_id:
                    found_task = True
                continue

            # 在token数量可承受范围内优先前文
            # 并且，在获得上下文内容时，下文内容中不出现<OUTLINE>
            if new_doc.meta['type'] == 'OUTLINE':
                new_doc.text = '...\n'
            md = new_doc.text + md
            if len(md) <= k:
                docs.append(new_doc)
                continue

            # 补充所有祖先标题
            doc_is_header = new_doc.meta['type'] == "heading"
            if doc_is_header:
                doc_level = new_doc.meta['attrs']['level']
                if last_header_level == None or doc_level <= last_header_level:
                    docs.append(new_doc)
                    last_header_level = doc_level

        return docs[::-1]

    def get_next_documents(self, index_doc: Union[str, Document]=None, k:int =200):
        """
        获得向后关联文档。
        
        推理能力较弱的模型，不可在上下文中出现 <OUTLINE></OUTLINE> 包含的扩写内容。
        否则模型将无视提示语中无需的扩写指令，对其展开扩写。
        """
        if index_doc is None:
            return []

        task_id = index_doc.meta['id'] if isinstance(index_doc, Document) else index_doc

        md = ""
        found_task = False
        docs = []

        for _doc in self.documents:
            new_doc = copy.deepcopy(_doc)
            if not found_task:
                if new_doc.meta['id'] == task_id:
                    found_task = True
                continue

            # 获得上下文内容时，下文内容中不出现<OUTLINE>
            if new_doc.meta['type'] == 'OUTLINE':
                new_doc.text = '...\n'
            md = new_doc.text + md
            if len(md) <= k:
                docs.append(new_doc)
            else:
                break

        return docs