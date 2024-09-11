import re
import copy
import os
import yaml
from typing import Iterator, List, Union, Optional
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_text_splitters import TextSplitter
from ..parser import parse_markdown, create_front_matter, list_markdown
from ...config import get_env
from ...utils import extract_text

class Markdown():
    def __init__(self, doc_str: str=None):
        self.documents = []
        self.doc_str = doc_str
        self.import_markdown(doc_str)

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
    def to_text(cls, documents: List[Document], sep: str="", with_front_matter: bool=False):
        if not documents:
            return ''

        meta0 = documents[0].metadata
        front_matter = ''
        if with_front_matter and 'type' in meta0 and meta0['type'] == 'front_matter':
            front_matter = create_front_matter(meta0)

        return front_matter + sep.join([d.page_content for d in documents])

    @property
    def text(self):
        return self.__class__.to_text(self.documents)

    @property
    def types(self):
        s = set()
        for d in self.documents:
            s.add(d.metadata['type'])
        print(s)

    def get_all(self, pattern: str=None):
        return [
            d
            for d in self.documents
            if re.search(pattern or '.*', d.page_content)
        ]

    def get_outline(self, pattern: str=None):
        return [
            d
            for d in self.documents
            if d.metadata['type'] == "OUTLINE"
            and re.search(pattern or '.*', d.page_content)
        ]
    
    def fetch_outline_task(self, outline_doc: Document, prev_k: int=800, next_k: int=200):
        """
        提取提纲内容。

        返回结果为 (draft: str, task: str)，其中：
        - draft 为结合了前后文和扩写位置说明的草稿
        - task 为具体的要求
        """
        if outline_doc.metadata['type'] != 'OUTLINE':
            raise  ValueError(f"Document's type Must be OUTLINE!")

        # 提取草稿
        docs = []

        docs.extend(self.get_prev_documents(outline_doc, k=prev_k))

        outline = Document(page_content="<<<YOUR_TEXT>>>\n\n", metadata={"type": "paragraph"})
        docs.append(outline)

        docs.extend(self.get_next_documents(outline_doc, k=next_k))

        draft = self.__class__.to_text(docs)

        # 提取任务
        tag_start = get_env("TEXTLONG_OUTLINE_START")
        tag_end = get_env("TEXTLONG_OUTLINE_END")
        md = self.__class__.to_text([outline_doc])
        task = extract_text(md, tag_start, tag_end)

        return (draft, task)

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
        
        prev_heading = next((doc for doc in reversed(prev_docs) if doc.metadata['type'] == 'heading'), None)
        next_heading = next((doc for doc in next_docs if doc.metadata['type'] == 'heading'), None)

        from_index = None
        if prev_heading:
            for i, d in enumerate(to_insert):
                if d.page_content.strip() == prev_heading.page_content.strip():
                    from_index = i + 1
                    break

        to_index = None
        if next_heading:
            for i, d in enumerate(reversed(to_insert)):
                if d.page_content.strip() == next_heading.page_content.strip():
                    to_index = i
                    break

        to_insert_docs = to_insert[from_index:to_index]

        ##
        # print("\n", "-"*80)
        # print(list_markdown([prev_heading, next_heading]))
        # print("\n", "-"*80)
        # print(list_markdown(to_insert[:3]))
        # print(list_markdown(to_insert[-3:]))
        # print("\n", "-"*80)
        # print(from_index, to_index)
        # print(list_markdown(to_insert_docs))

        self.documents = prev_docs + to_insert_docs + next_docs
        return to_insert_docs

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

        for _doc in self.documents[::-1]:
            new_doc = copy.deepcopy(_doc)
            if not found_task:
                if new_doc.metadata['id'] == task_id:
                    found_task = True
                continue

            # 在token数量可承受范围内优先前文
            # 并且，在获得上下文内容时，下文内容中不出现<OUTLINE>
            if new_doc.metadata['type'] == 'OUTLINE':
                new_doc.page_content = '...\n'
            md = new_doc.page_content + md
            if len(md) <= k:
                docs.append(new_doc)
                continue

            # 补充所有祖先标题
            doc_is_header = new_doc.metadata['type'] == "heading"
            if doc_is_header:
                doc_level = new_doc.metadata['attrs']['level']
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

        task_id = index_doc.metadata['id'] if isinstance(index_doc, Document) else index_doc

        md = ""
        found_task = False
        docs = []

        for _doc in self.documents:
            new_doc = copy.deepcopy(_doc)
            if not found_task:
                if new_doc.metadata['id'] == task_id:
                    found_task = True
                continue

            # 获得上下文内容时，下文内容中不出现<OUTLINE>
            if new_doc.metadata['type'] == 'OUTLINE':
                new_doc.page_content = '...\n'
            md = new_doc.page_content + md
            if len(md) <= k:
                docs.append(new_doc)
            else:
                break

        return docs