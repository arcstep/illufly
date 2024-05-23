import re
from typing import List, Union
from langchain_core.documents import Document

class TreeDocuments():
    def __init__(self, doc_str: str, start_id = None, doc_type="md"):
        if doc_type == "md":
            self.documents = self.parse_markdown(doc_str)
        elif doc_type == "html":
            self.documents = self.parse_html(doc_str)
        
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

    def parse_html(self, html_document: str) -> List[Document]:
        from bs4 import BeautifulSoup, NavigableString

        soup = BeautifulSoup(html_document, 'html.parser')

        documents = []
        indices = {'H1': 0, 'H2': 0, 'H3': 0, 'H4': 0, 'H5': 0, 'H6': 0, 'paragraph': 0}
        current_indices = {'H1': 0, 'H2': 0, 'H3': 0, 'H4': 0, 'H5': 0, 'H6': 0, 'paragraph': 0}

        def parse_node(node, parent_type=None):
            nonlocal indices, current_indices
            if isinstance(node, NavigableString):
                if node.strip():
                    type_ = 'paragraph'
                    indices[type_] += 1
                    current_indices[type_] = indices[type_]
                    id_ = '.'.join(str(current_indices[t]) for t in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'paragraph'] if current_indices[t] > 0)
                    documents.append(Document(page_content=node.strip(), metadata={'type': type_, 'id': id_}))
                return
            if node.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p']:
                type_ = 'H' + node.name[1] if node.name[0] == 'h' else 'paragraph'
                indices[type_] += 1
                current_indices[type_] = indices[type_]
                if type_ in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']:
                    indices = {key: (0 if key > type_ else value) for key, value in indices.items()}
                id_ = '.'.join(str(current_indices[t]) for t in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'paragraph'] if current_indices[t] > 0)
                documents.append(Document(page_content=node.text, metadata={'type': type_, 'id': id_}))
            elif node.name == 'div':
                for child in node.children:
                    parse_node(child, parent_type)

        for child in soup.body.children:
            parse_node(child)

        return documents

    def build_index(self, start_id: str=None):
        indices = {f'H{i}': 0 for i in range(1, 9)}
        indices['paragraph'] = 0
        last_heading = None
        prefix = start_id if start_id else ""

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
            doc.metadata['id'] = prefix + ('' if prefix == "" else '.') + '.'.join(str(indices[f'H{i}']) for i in range(1, int(last_heading[1:]) + 1)) + ('.' + str(indices['paragraph']) if type_ == 'paragraph' else '')

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
