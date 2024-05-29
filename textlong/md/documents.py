import re
from typing import List, Union
from langchain_core.documents import Document

class IntelliDocuments():
    def __init__(self, doc_str: str=None, start_id="1", llm=None):
        self.llm = llm
        self.documents = []
        self.import_markdown(doc_str, start_id)

    def import_markdown(self, doc_str: str=None, start_id="1"):
        """
        导入Markdown文档。
        """
        if doc_str != None:
            self.documents += self.parse_markdown(doc_str)
            
            if self.documents:
                self.build_index(start_id)
        
        return self.documents

    @classmethod
    def parse_markdown(cls, doc_str: str) -> List[Document]:
        """
        解析 Markdown 文件。
        给定的 Markdown 中的第一个标题应当是最大的标题。
        """

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
        max_heading = 999
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
        if documents and max_heading != 999 and (documents[0].metadata['type'] != f'H{max_heading}'):
            documents.insert(0, Document(page_content='<<TITLE>>', metadata={'type': f'H{max_heading}'}))

        return documents

    def build_index(self, start_id: str="1.1"):
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

        for doc in self.documents:
            type_ = doc.metadata.get('type')
            if type_ in indices:
                if type_.startswith('H'):
                    # Increment the current level index
                    indices[type_] += 1
                    # Save the current level index
                    last_index = indices[type_]
                    # Reset the indices of the lower levels
                    for lower_type in [f'H{i}' for i in range(int(type_[1:]) + 1, 9)] + ['paragraph']:
                        indices[lower_type] = 0
                    last_heading = type_
                    # Update tail_ids, middle, tail and doc.metadata['id']
                    tail_ids = [str(indices[f'H{i}']) if i < int(last_heading[1]) else str(last_index) for i in range(1, int(last_heading[1]) + 1)]
                    middle = f"{int(tail_ids[0]) - 1 + start_int}"
                    tail = ".".join(tail_ids[1:])
                    # print(f'{prefix or "<EMPTY>"}-{middle}({tail_ids[0]}/{start_int})-{tail}')
                    doc.metadata['id'] = ".".join([e for e in [prefix, middle, tail] if e != ""])
                elif type_ == 'paragraph' and last_heading:
                    # Set the paragraph index to 0
                    indices['paragraph'] = 0
                    # Update tail_ids and doc.metadata['id']
                    tail_ids.append(str(indices['paragraph']))
                    tail = ".".join(tail_ids[1:])
                    doc.metadata['id'] = ".".join([e for e in [prefix, middle, tail] if e != ""])
                    # print(f"{prefix or 'EMPTY'}-{middle}-{tail_ids}")
                    tail_ids.pop()

    def get_documents(self, id: Union[str, List[str]]="1", node_type: Union[str, List[str]]=None):
        """获得文档子树"""

        if isinstance(id, str):
            id = [id]
        if isinstance(node_type, str):
            node_type = [node_type]
        if node_type == None:
            node_type = ['H', 'par'] # [H1,H2,...H6, paragraph]

        return [
            doc
            for doc in self.documents
            if doc.metadata
            and 'id' in doc.metadata
            and any(doc.metadata['id'].startswith(i) for i in id)
            and 'type' in doc.metadata
            and any(doc.metadata['type'].startswith(i) for i in node_type)
        ]

    def replace_documents(self, node_id: str, documents: List[Document], sorting=True):
        """在指定位置替换文档子树"""

        self.remove_documents(node_id, sorting=False)
        self.insert_documents(node_id, documents, sorting=False)
        if sorting:
            self.documents.sort(key=lambda doc: doc.metadata['id'])

        return self.documents

    def insert_documents(self, node_id: str, documents: List[Document], sorting=True):
        """添加子树，并按照 Document.metadata['id'] 重新排序"""

        if node_id is None:
            self.documents.extend(documents)
        else:
            for i, doc in enumerate(self.documents):
                if doc.metadata['id'] == node_id:
                    for j, new_doc in enumerate(documents):
                        self.documents.insert(i + j, new_doc)
                    break

        if sorting:
            self.documents.sort(key=lambda doc: doc.metadata['id'])

        return self.documents

    def remove_documents(self, node_id: str, sorting = True):
        """删除指定的子树"""

        indices = [i for i, doc in enumerate(self.documents) if doc.metadata['id'].startswith(node_id)]
        if indices:
            for index in reversed(indices):
                del self.documents[index]
            if sorting:
                self.documents.sort(key=lambda doc: doc.metadata['id'])

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

    def get_markdown(self, id: Union[str, List[str]]=None, node_type: Union[str, List[str]]=None, with_number: bool=False):
        """
        导出 Markdown 文本。
        """

        docs = self.get_documents(node_type=node_type) if id == None else self.get_documents(id, node_type=node_type)
        md = ""
        
        for doc in docs:
            md += self._get_text(doc, with_number)
        
        return md

    def get_todo_ids(self, start_id="1"):
        """获得提纲任务"""
        tasks = []
        docs = self.get_documents(id=start_id, node_type="H")
        len_docs = len(docs)
        for i, doc in enumerate(docs):
            if doc.metadata and doc.metadata['id']:
                # 检查是否有子标题
                if i + 1 < len_docs and not docs[i + 1].metadata['id'].startswith(doc.metadata['id'] + "."):
                    tasks.append(doc.metadata['id'])
                elif i + 1 == len_docs:
                    tasks.append(doc.metadata['id'])

        return tasks
    
    def _get_text(self, document: Document=None, with_number: bool=False):
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

                # 检查是否是兄弟节点或祖先节点
                id_parts = id.split('.')
                ancestor_id = ".".join(ancestor_ids)
                parent_id = ".".join(id_parts[:-1])
                to_compare = parent_id if len(id_parts)==len(ancestor_ids) + 1 else id
                if ancestor_id.startswith(to_compare):
                    md += self._get_text(doc, True)
        
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
                text = self._get_text(doc, with_number)
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