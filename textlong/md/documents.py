import re
import copy
import os
from typing import List, Union
from langchain_core.documents import Document
from ..parser import parse_markdown
from ..utils import raise_not_install
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
        return "".join([d.page_content for d in self.documents if d.metadata['type'] != "OUTLINE"])

    def get_outline_task(self):
        """
        获得OUTLINE扩写任务清单。
        如果没有指定title，就返回所有任务，否则返回匹配到的任务。
        """

        return [d for d in self.documents if d.metadata['type'] == "OUTLINE"]
    
    def get_task_index(self, task_doc: Union[str, Document]):
        """
        获得任务索引。
        """
        task_id = task_doc.metadata['id'] if isinstance(task_doc, Document) else task_doc
        for i, doc in enumerate(self.documents):
            if doc.metadata['id'] == task_id:
                return i

        return None

    def insert_documents(self, task_doc: Union[str, Document]=None, docs: List[Document]=None):
        """
        插入文档对象列表。
        """
        index = self.get_task_index(task_doc)
        if index != None:
            self.documents = self.documents[:index] + docs + self.documents[index+1:]

        return self.documents
    
    def get_relevant_documents(self, task_doc: Union[str, Document]=None, k=1000):
        """
        获得与扩写强关联的文档。
        为了保持扩写任务的上下文连续，这包括扩写位置所有的前序兄弟标题和祖先标题，并在token可承受的范围内尽量包含前文。
        """
        if task_doc is None:
            return []

        task_id = task_doc.metadata['id'] if isinstance(task_doc, Document) else task_doc

        md = ""
        found_task = False
        not_over_k = True
        last_header_level = None
        docs = []

        for doc in self.documents[::-1]:
            if not found_task:
                if doc.metadata['id'] == task_id:
                    found_task = True
                continue

            # 在token可承受范围内优先前文，无论是何种样式
            if not_over_k:
                md = doc.page_content + md
                if len(md) > k:
                    not_over_k = False
                else:
                    if doc.metadata['type'] != 'OUTLINE':
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
