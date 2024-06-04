from typing import Iterable, Dict, Any
import re
import time
from mistune import markdown
from mistune.renderers.markdown import MarkdownRenderer
from mistune.core import BlockState
from langchain_core.documents import Document

class SegmentsRenderer(MarkdownRenderer):
    def __init__(self, doc_id_generator):
        super().__init__()
        self.doc_id_generator = doc_id_generator

    def __call__(self, tokens: Iterable[Dict[str, Any]], state: BlockState) -> str:
        documents = []
        for tok in tokens:
            md = self.render_token(tok, state)
            doc_id = next(self.doc_id_generator)
            tok.update({"id": doc_id})
            documents.append(Document(page_content=md, metadata=tok))
        return documents

def parse_markdown(text):
    doc_id_generator = get_document_id()
    pattern = re.compile(r'(.*?)(<OUTLINE>(.*?)</OUTLINE>)(.*)', re.DOTALL)
    documents = []
    while '<OUTLINE>' in text and '</OUTLINE>' in text:
        match = pattern.match(text)
        if match:
            before, outline, outline_content, after = match.groups()
            if before:
                documents.extend(markdown(before, renderer=SegmentsRenderer(doc_id_generator)))
            doc_id = next(doc_id_generator)
            doc = Document(page_content=outline_content, metadata={"id":doc_id, "type": 'OUTLINE'})
            documents.append(doc)
            text = after
    if text:
        documents.extend(markdown(text, renderer=SegmentsRenderer(doc_id_generator)))
    return documents

def get_document_id():
    counter = 0
    while True:
        yield f'{int(time.time())}-{counter}'
        counter += 1