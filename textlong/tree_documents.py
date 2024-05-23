import re
from typing import List, Union
from langchain_core.documents import Document

class TreeDocuments():
    def __init__(self, doc_str: str, start_id = "1"):
        self.documents = self.parse_markdown(doc_str)
        
        if self.documents:
            self.build_index(start_id)

    def parse_markdown(self, doc_str: str) -> List[Document]:
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
        for match in matches:
            if match[0]:  # This is a title
                type_ = 'H' + str(len(match[0]))
                content = match[1]
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

        return documents

    def build_index(self, start_id: str="1"):
        indices = {f'H{i}': 0 for i in range(1, 9)}
        indices['paragraph'] = 0
        last_heading = None

        start_ids = start_id.split(".")
        prefix = ".".join(start_ids[:-1])
        start_int = int(start_ids[-1]) if start_ids[-1].isdigit() else 0

        for doc in self.documents:
            type_ = doc.metadata.get('type')
            if type_ in indices:
                if type_.startswith('H'):
                    indices[type_] += 1
                    # Reset the indices of the lower levels
                    for lower_type in [f'H{i}' for i in range(int(type_[1:]) + 1, 9)] + ['paragraph']:
                        indices[lower_type] = 0
                    last_heading = type_
                elif type_ == 'paragraph' and last_heading:
                    indices['paragraph'] += 1

            if last_heading:
                tail_ids = ('.'.join(str(indices[f'H{i}']) for i in range(1, int(last_heading[1:]))) + \
                    ('.' + str(indices['paragraph']) if type_ == 'paragraph' else '')).split(".")
                middle = f"{(int(tail_ids[0]) if tail_ids[0] != '' else 0) + start_int}"
                tail = ".".join(tail_ids[1:])
                doc.metadata['id'] = ".".join([e for e in [prefix, middle, tail] if e != ""])

    def get_documents(self, id: Union[str, List[str]]="1", node_type: Union[str, List[str]]=None):
        """获得文档子树"""

        if isinstance(id, str):
            id = [id]
        if isinstance(node_type, str):
            node_type = [node_type]
        if node_type == None:
            node_type = ['H', 'p'] # [H1,H2,...H6, paragraph]
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
        """在指定位置替换子树"""
        self.remove_documents(node_id, sorting=False)
        self.insert_documents(documents, sorting=False)
        if sorting:
            self.documents.sort(key=lambda doc: doc.metadata['id'])
        
        return self.documents

    def insert_documents(self, documents: List[Document], sorting=True):
        """添加子树，并按照 Document.metadata['id'] 重新排序"""
        self.documents.extend(documents)
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
