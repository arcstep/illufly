import re
from typing import List, Union
from langchain_core.documents import Document
import copy

class IntelliDocuments():
    def __init__(self, doc_str: str=None, start_id="1", llm=None):
        self.llm = llm
        self.documents = []

        if doc_str != None:
            documents = self.parse_markdown(doc_str)
            self.documents.extend(documents)
            # self.insert_documents(documents, start_id)

    def import_markdown(self, doc_str: str=None, to_id="99999"):
        """
        导入Markdown文档。
        """
        if doc_str != None:
            document = self.parse_markdown(doc_str)
            self.replace_documents(document, to_id)
            
        return self.documents

    @classmethod
    def parse_markdown(cls, doc_str: str) -> List[Document]:
        """
        解析 Markdown 文件。
        给定的 Markdown 中的第一个标题应当是最大的标题。
        """

        if not isinstance(doc_str, str):
            raise ValueError("parse_markdown: doc_str ONLY accept str !")

        # Step 1: Replace the content in ``` <<content>> ``` with a special marker
        pattern = r'```.*?```'
        matches = re.findall(pattern, doc_str, re.DOTALL)
        code_blocks = matches.copy()  # Save the code block content
        for i, match in enumerate(matches):
            doc_str = doc_str.replace(match, f'CODEBLOCK{i}')

        # Step 2: Parse the markdown document as before
        pattern = r'(#{1,3})\s*(.*?)\n|((?:(?<=\n)|^)(?!\s*#).*?(?=\n\s*#|$))'
        matches = re.findall(pattern, doc_str, re.DOTALL)
        documents = []
        max_heading = 9999
        for match in matches:
            if match[0]:  # This is a title
                type_ = 'H' + str(len(match[0]))
                content = match[1]
                max_heading = min(max_heading, len(match[0]))
            else:  # This is a paragraph
                type_ = 'paragraph'
                content = match[2]
            content = content.strip()
            if content:  # Ignore empty content
                documents.append(Document(page_content=content, metadata={'type': type_}))

        # Step 3: Replace the special markers with the original content
        for i, code_block in enumerate(code_blocks):
            for doc in documents:
                doc.page_content = doc.page_content.replace(f'CODEBLOCK{i}', code_block)

        # Step 4: Check the first document's type
        # print('H' + str(max_heading))
        # if documents and (documents[0].metadata['type'] != f'H{max_heading}'):
        #     documents.insert(0, Document(page_content='<<TITLE>>', metadata={'type': f'H{max_heading}'}))

        return documents

    @classmethod
    def build_index(self, documents: List[Document], start_id: str="1"):
        """构建层级编号"""

        indices = {f'H{i}': 0 for i in range(1, 9)}  # Initialize all indices to 0
        indices['paragraph'] = 0
        last_heading = None
        last_index = 0

        start_ids = start_id.split(".")
        start_int = int(start_ids[-1]) if start_ids[-1].isdigit() else 0
        prefix = ".".join(start_ids[:-1])

        tail_ids = []
        tail = ""
        middle = ""

        for doc in documents:
            type_ = doc.metadata.get('type')
            if type_ in indices:
                if type_.startswith('H'):
                    indices[type_] += 1
                    last_index = indices[type_]
                    for lower_type in [f'H{i}' for i in range(int(type_[1:]) + 1, 9)] + ['paragraph']:
                        indices[lower_type] = 0
                    last_heading = type_
                    tail_ids = [str(indices[f'H{i}']) if i < int(last_heading[1]) else str(last_index) for i in range(1, int(last_heading[1]) + 1)]
                    middle = f"{int(tail_ids[0]) - 1 + start_int}"
                    tail = ".".join(tail_ids[1:])
                    # print(f'{prefix or "<EMPTY>"}-{middle}({tail_ids[0]}/{start_int})-{tail}')
                    doc.metadata['id'] = ".".join([e for e in [prefix, middle, tail] if e != ""])
                elif type_ == 'paragraph' and last_heading:
                    indices['paragraph'] = 0
                    tail_ids.append(str(indices['paragraph']))
                    tail = ".".join(tail_ids[1:])
                    doc.metadata['id'] = ".".join([e for e in [prefix, middle, tail] if e != ""])
                    # print(f"{prefix or 'EMPTY'}-{middle}-{tail_ids}")
                    tail_ids.pop()
                else:
                    doc.metadata['id'] = '0'

        return documents

    def get_documents_range(self, title: str=None):
        start_index = None
        end_index = None
        if title != None:
            last_header_doc = None
            for i, doc in enumerate(self.documents):
                print(i, doc)
                with_header = doc.metadata['type'].startswith("H")
                if doc.page_content.startswith(title):
                    start_index = i
                    end_index = i
                    if with_header:
                        last_header_doc = doc
                    continue
                if last_header_doc:
                    if with_header and doc.metadata['type'] > last_header_doc.metadata['type']:
                        continue
                    elif not with_header:
                        continue
                    # 标题已入栈且未找到更深标题或段落时退出
                    end_index = i
                    break
        return (start_index, end_index if start_index != end_index else None)

    def get_documents(self, title: str=None, node_type: Union[str, List[str]]=None):
        """获得文档子树"""
        start_index, end_index = self.get_documents_range(title)
        return self.documents[start_index:end_index]
    
    def replace_documents(self, new_docs: List[Document], title: str=None):
        """在指定位置替换文档子树"""
        
        start_index, end_index = self.get_documents_range(title)
        if start_index == None or end_index == None:
            self.documents = self.documents + new_docs
        else:
            self.documents = self.documents[:start_index] + new_docs + self.documents[end_index:None]
        return self.documents

    def insert_documents(self, new_docs: List[Document], title: str=None):
        """插入文档到指定位置"""

        start_index, end_index = self.get_documents_range(title)
        if start_index == None or end_index == None:
            self.documents = self.documents + new_docs
        else:
            self.documents = self.documents[:start_index] + new_docs + self.documents[start_index:]
        return self.documents

    def remove_documents(self, title: str):
        """删除指定的子树"""
        start_index, end_index = self.get_documents_range(title)
        if start_index and end_index:
            self.documents = self.documents[:start_index] + self.documents[end_index:]
        return self.documents

    def get_markdown_header(self, document: Document=None, with_number: bool=True):
        if document == None:
            return ''
        
        id = ''
        type = ''
        if document.metadata:
            id = (document.metadata['id'] + " ") if with_number else ""
            type = document.metadata['type']

        if type == "H1":
            header = f'# {id}'
        elif type == "H2":
            header = f'## {id}'
        elif type == "H3":
            header = f'### {id}'
        elif type == "H4":
            header = f'#### {id}'
        elif type == "H5":
            header = f'##### {id}'
        elif type == "H6":
            header = f'###### {id}'
        elif type == "H7":
            header = f'####### {id}'
        elif type == "H8":
            header = f'####### {id}'
        else:
            header = ''
        
        return header

    def get_markdown(self, title: Union[str, List[str]]=[], node_type: Union[str, List[str]]=None, with_number: bool=False):
        """
        导出 Markdown 文本。
        """

        docs = self.get_documents(node_type=node_type) if title == None else self.get_documents(title, node_type=node_type)
        md = ""
        
        for doc in docs:
            md += self.get_node_text(doc, with_number)
        
        return md

    def get_trunk_and_leaf_nodes(self, start_id=[]):
        """获得提纲任务"""
        trunk_nodes = []
        leaf_nodes = []
        docs = self.get_documents(id=start_id, node_type="H")
        len_docs = len(docs)
        for i, doc in enumerate(docs):
            if doc.metadata and doc.metadata['id']:
                # 检查是否有子标题
                if i + 1 < len_docs and not docs[i + 1].metadata['id'].startswith(doc.metadata['id'] + "."):
                    leaf_nodes.append(doc)
                elif i + 1 == len_docs:
                    leaf_nodes.append(doc)
                else:
                    trunk_nodes.append(doc)

        return trunk_nodes, leaf_nodes
    
    def get_node_text(self, document: Document=None, with_number: bool=False):
        if document and document.metadata and document.page_content:
            if document.metadata['type'] and document.metadata['type'].startswith("H"):
                return "\n" \
                    + self.get_markdown_header(document, with_number) + document.page_content \
                    + "\n\n"
            else:
                return document.page_content + "\n"
        return ""

    def get_relevant_documents(self, to_id="9999999", with_number: bool=False):
        """获得相关性较强的文档"""
        md = ""

        ancestor_ids = to_id.split('.')[:-1]
        for doc in self.documents:
            if doc.metadata and doc.metadata['id']:
                # 如果 ID 以 '.0' 结尾，就去掉 '.0'
                id = doc.metadata['id'][:-2] if doc.metadata['id'].endswith('.0') else doc.metadata['id']
                if to_id.startswith(id):
                    md += self.get_node_text(doc, True)

        return md

    def get_prev_markdown(self, to_id="9999999", k=1500, with_number: bool=False):
        """
        获得已完成的最新扩写。
        """
        md = ""
        length = 0

        # 从后往前遍历文档列表
        for doc in reversed(self.documents):
            if is_prev_id(doc.metadata['id'], to_id):
                text = self.get_node_text(doc, with_number)
                length += len(text)
                md = text + md

                # 如果累积长度超过 k，就终止
                if length > k:
                    break

        if length > k:
            return "(省略前文）\n...\n" + md
        else:
            return md

def is_prev_id(id1, id2):
    """
    比较两个形如 "2.3.4" 的 ID，如果 id1 小于 id2，返回 True，否则返回 False。
    """
    list1 = list(map(int, id1.split('.')))
    list2 = list(map(int, id2.split('.')))

    return list1 < list2