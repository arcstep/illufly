import re
import copy
import os
from typing import List, Union
from langchain_core.documents import Document
from ..parser import parse_markdown
from ..utils import raise_not_install, markdown
from ..config import get_textlong_folder, get_textlong_doc, _TEMP_FOLDER_NAME

class IntelliDocuments():
    def __init__(self, doc_str: str=None):
        self.documents = []
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

    @property
    def markdown(self):
        return markdown(self.documents)

    def get_outline_task(self):
        """
        获得OUTLINE扩写任务清单。
        如果没有指定title，就返回所有任务，否则返回匹配到的任务。
        """

        return [
            (d, i)
            for i, d in enumerate(self.documents) 
            if d.metadata['type'] == "OUTLINE"
        ]
    
    def get_task_index(self, index_doc: Union[str, Document]):
        """
        获得任务索引。
        """
        task_id = index_doc.metadata['id'] if isinstance(index_doc, Document) else index_doc
        for i, doc in enumerate(self.documents):
            if doc.metadata['id'] == task_id:
                return i

        return None

    def insert_documents(self, index_doc: Union[str, Document]=None, docs: Union[str, List[Document]]=None):
        """
        插入文档对象。
        """
        return self._replace_documents(index_doc, docs, reserve=True)

    def replace_documents(self, index_doc: Union[str, Document]=None, docs: Union[str, List[Document]]=None):
        """
        替换文档对象。
        """
        return self._replace_documents(index_doc, docs, reserve=False)

    def _replace_documents(self, index_doc: Union[str, Document]=None, docs: Union[str, List[Document]]=None, reserve = False):
        to_insert = parse_markdown(docs) if isinstance(docs, str) else docs
        index = self.get_task_index(index_doc)
        if index != None:
            self.documents = self.documents[:index] + to_insert + self.documents[index + (0 if reserve else 1):]
        else:
            info = index_doc.page_content if isinstance(index_doc, Document) else index_doc
            raise ValueError(f"Not Found: {info}")

        return self.documents

    def get_prev_documents(self, index_doc: Union[str, Document]=None, k: int=800):
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