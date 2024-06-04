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

    def get_documents_range(self, title: str=None):
        """
        获得文档筛查的索引范围。
        """

        start_index = None
        end_index = None
        if title != None:
            last_header_doc = None
            for i, doc in enumerate(self.documents):
                # print(i, doc)
                doc_type = doc.metadata['type']
                if start_index == None and doc.page_content.startswith(title):
                    start_index = i
                    end_index = i
                    if doc_type == 'heading':
                        last_header_doc = doc
                    continue
                if start_index != None and last_header_doc:
                    doc_level = doc.metadata['attrs']['level'] if 'attrs' in doc.metadata and 'level' in doc.metadata['attrs'] else None
                    last_header_doc_level = last_header_doc.metadata['attrs']['level'] if 'attrs' in last_header_doc.metadata and 'level' in last_header_doc.metadata['attrs'] else None
                    if doc_type == 'heading' and doc_level and last_header_doc_level and doc_level > last_header_doc_level:
                        continue
                    elif doc_type != 'heading':
                        continue
                    # 标题已入栈且未找到更深标题或段落时退出
                    end_index = i
                    break
            if start_index == None:
                raise ValueError("Can't find title: ", title)
        
        return (start_index, end_index if start_index != end_index else None)

    def get_documents(self, title: str=None, node_type: Union[str, List[str]]=None):
        """
        获得文档子树。
        """
        
        if node_type == None:
            types = ['H', 'para']
        elif isinstance(node_type, str):
            types = [node_type]
        elif isinstance(node_type, List):
            types = node_type
        else:
            raise(ValueError(f"Invalid node_type: {node_type}"))

        pattern = re.compile(r'(' + '|'.join(types) + ')')
        
        start_index, end_index = self.get_documents_range(title)
        return [d for d in self.documents[start_index:end_index] if pattern.match(d.metadata['type'])]

    def replace_documents(self, new_docs: List[Document], title: str=None,):
        """
        在指定位置替换文档子树。
        """
        
        IntelliDocuments.update_action(new_docs)

        if title == None:
            self.documents += new_docs
        else:
            start_index, end_index = self.get_documents_range(title)

            if start_index == None and end_index == None:
                self.documents = new_docs
            elif start_index == None and end_index != None:
                self.documents = new_docs + self.documents[end_index:None]
            elif start_index != None and end_index == None:
                self.documents = self.documents[:start_index] + new_docs
            else:
                self.documents = self.documents[:start_index] + new_docs + self.documents[end_index:None]

        return self.documents

    def insert_documents(self, new_docs: List[Document], title: str=None):
        """
        插入文档到指定位置。
        """
        
        IntelliDocuments.update_action(new_docs)

        if title == None:
            self.documents += new_docs
        else:
            start_index, end_index = self.get_documents_range(title)

            if start_index == None and end_index != None:
                self.documents = self.documents[:end_index] + new_docs + self.documents[end_index:None]
            elif start_index != None:
                self.documents = self.documents[:start_index] + new_docs + self.documents[start_index:None]

        return self.documents

    def remove_documents(self, title: str):
        """
        删除指定的子树。
        """

        start_index, end_index = self.get_documents_range(title)
        if start_index and end_index:
            self.documents = self.documents[:start_index] + self.documents[end_index:]
        return self.documents

    @property
    def markdown(self):
        return "".join([d.page_content for d in self.documents if d.metadata['type'] != "OUTLINE"])

    def get_outline_task(self):
        """
        获得OUTLINE扩写任务清单。
        如果没有指定title，就返回所有任务，否则返回匹配到的任务。
        """

        return [d.page_content for d in self.documents if d.metadata['type'] == "OUTLINE"]
    
    def get_relevant_documents(self, task_doc: Document=None):
        if doc is None:
            return []

        docs = []
        found_doc = []
        found_header = None

        for doc in self.documents[::-1]:
            found_doc.append(doc)
            doc_is_header = doc.metadata['type'] == "heading"
            doc_level = doc.metadata['attrs']['level'] if 'attrs' in doc.metadata and 'level' in doc.metadata['attrs'] else None

            if docs and doc.metadata['id'] == task_doc.metadata['id']:
                # 找到匹配文档
                docs += found_doc
                if doc_is_header:
                    found_header = doc_level
                    found_doc = []
            elif docs:
                # 查找关联文档
                if found_header != None or (doc_is_header and doc_level < found_header):
                    docs += found_doc
                    found_header = doc_type

            if doc_is_header:
                found_doc = []

        return docs[::-1]

    def get_prev_documents(self, title: str=None, k=1000):
        """
        获得已完成的最新扩写。
        """

        documents = []
        found = False

        md = ""
        for doc in self.documents[::-1]:
            if not documents and doc.page_content.startswith(title):
                found = True
                continue
            if found:
                documents.append(doc)
                md = self.get_node_text(doc) + md
                if len(md) > k:
                    break

        return documents[::-1]
