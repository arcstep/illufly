from typing import Dict, Any, List, Union
from ..utils import minify_text, create_id_generator
import json
import time

doc_id_generator = create_id_generator()

class Document():
    def __init__(self, text: str=None, index: str=None, meta: Dict[str, Any] = None):
        self.text = text or ""
        self.index = index or ""
        self.meta = {**(meta or {})}
        if 'id' not in self.meta:
            self.meta['id'] = next(doc_id_generator)

    def __repr__(self):
        meta_converted = [k for k, _v in self.meta.items()]
        return f"Document(text=\"{minify_text(self.text)}\", meta={meta_converted})"

    def __str__(self):
        return self.text
    
    def __len__(self):
        return len(self.text)

def convert_to_documents_list(docs: Union[str, List[str], List[Document]]):
    if isinstance(docs, str):
        docs = [docs]

    if not isinstance(docs, list):
        raise ValueError("docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")
    
    docs_list = []
    for doc in docs:
        if isinstance(doc, str):
            doc = Document(doc, meta={'source': '__rerank__'})
        if not isinstance(doc, Document):
            raise ValueError("docs 必须是字符串或 Document 类型列表，但实际为: {type(docs)}")

        docs_list.append(doc)

    return docs_list
