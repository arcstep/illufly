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

    def import_markdown(self, doc_str: str=None, action: str="import"):
        """
        导入Markdown文档。
        """
        
        filename = doc_str
        if filename and os.path.isfile(filename) and os.path.exists(doc_str):
            if filename.endswith(".md") or filename.endswith(".MD"):
                file_path = filename
            elif filename.endswith(".docx"):
                file_path = self.parse_docx(filename)

            with open(file_path, 'r') as file:
                doc_str = file.read()

        if doc_str:
            documents = parse_markdown(doc_str)
            self.insert_documents(documents, title=None)
            IntelliDocuments.update_action(self.documents, action)

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
                doc_level = doc.metadata['attrs']['level']
                if start_index == None and doc.page_content.startswith(title):
                    start_index = i
                    end_index = i
                    if doc_type == 'heading':
                        last_header_doc = doc
                    continue
                if start_index != None and last_header_doc:
                    if doc_type == 'heading' and doc_level > last_header_doc.metadata['attrs']['level']:
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

    def replace_documents(self, new_docs: List[Document], title: str=None, action="replace"):
        """
        在指定位置替换文档子树。
        """
        
        IntelliDocuments.update_action(new_docs, action)

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

    def insert_documents(self, new_docs: List[Document], title: str=None, action="insert"):
        """
        插入文档到指定位置。
        """
        
        IntelliDocuments.update_action(new_docs, action)

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

    @classmethod
    def update_action(cls, docs, action: str):
        for d in docs:
            d.metadata['action'] = action

    @classmethod
    def get_markdown_header(cls, document: Document=None):
        if document == None:
            return ''
        
        prefix = ''
        type = document.metadata['type'] if document.metadata and 'type' in document.metadata else ''

        if type == "H1":
            header = f'# {prefix}'
        elif type == "H2":
            header = f'## {prefix}'
        elif type == "H3":
            header = f'### {prefix}'
        elif type == "H4":
            header = f'#### {prefix}'
        elif type == "H5":
            header = f'##### {prefix}'
        elif type == "H6":
            header = f'###### {prefix}'
        elif type == "H7":
            header = f'####### {prefix}'
        elif type == "H8":
            header = f'######## {prefix}'
        else:
            header = ''
        
        return header

    @classmethod
    def get_node_text(cls, document: Document=None):
        if document and document.page_content:
            if document.metadata and document.metadata['type'] and document.metadata['type'].startswith("H"):
                return "\n" \
                    + cls.get_markdown_header(document) + document.page_content \
                    + "\n\n"
            else:
                return document.page_content + "\n"
        return ""
    
    @property
    def markdown(self):
        return self.__class__.get_markdown(self.documents)

    @classmethod
    def get_markdown(cls, docs: List[Document]=None):
        """
        导出 Markdown 文本。
        """

        md = ""
        if docs:
            for doc in docs:
                md += cls.get_node_text(doc)
        
        return md

    def get_leaf_outline(self):
        """
        获得叶子节点上的提纲任务清单。
        适合主从双线任务写作，在“主文档”中提取任务，获得任务列表，在一个循环中执行“从文档”任务。
        """

        leaf_documents = []
        last_header_doc = None

        for i, doc in enumerate(self.documents):
            # print(i, doc, last_header_doc.metadata['type'] if last_header_doc else '')
            if doc.metadata['type'].startswith("H"):
                if last_header_doc == None:
                    last_header_doc = doc
                    continue
                if doc.metadata['type'] <= last_header_doc.metadata['type']:
                    leaf_documents.append(last_header_doc)
                last_header_doc = doc

        if last_header_doc:
            leaf_documents.append(last_header_doc)

        return leaf_documents

    def get_branch_outline(self, header="H1"):
        """
        获得主干节点上的提纲任务清单。
        默认提取第一层级内容。
        """

        return self.get_documents(node_type=header)
    
    def get_relevant_documents(self, title: str=None):
        if title is None:
            return []

        documents = []
        found_doc = []
        found_header = None

        for doc in self.documents[::-1]:
            found_doc.append(doc)
            doc_type = doc.metadata['type']
            doc_is_header = doc_type.startswith('H')

            if not documents and doc.page_content.startswith(title):
                # 找到匹配文档
                documents += found_doc
                if doc_type and doc_is_header:
                    found_header = doc_type
                    found_doc = []
            elif documents:
                # 查找关联文档
                if not found_header or (doc_is_header and doc_type < found_header):
                    documents += found_doc
                    found_header = doc_type

            if doc_is_header:
                found_doc = []

        return documents[::-1]

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
