from typing import Iterable, Dict, Any
import re
from mistune import markdown
from mistune.renderers.markdown import MarkdownRenderer
from mistune.core import BlockState
from langchain_core.documents import Document

class SegmentsRenderer(MarkdownRenderer):
    def create_document(self, content, type, attrs=None):
        if content:
            doc = Document(page_content=content, metadata={"type": type, "attrs": attrs})
            yield doc

    def __call__(self, tokens: Iterable[Dict[str, Any]], state: BlockState) -> str:
        documents = []
        out = ""
        for tok in tokens:
            if tok['type'] in ['heading', 'block_code', 'image']:
                documents.extend(self.create_document(out, 'text'))
                out = self.render_token(tok, state)
                documents.extend(self.create_document(out, tok['type'], tok['attrs'] if 'attrs' in tok else None))
                out = ""
            else:
                out += self.render_token(tok, state)
        documents.extend(self.create_document(out, 'text'))
        return documents

def parse_markdown(text):
    pattern = re.compile(r'(.*?)(<TEXTLONG-OUTLINE>(.*?)</TEXTLONG-OUTLINE>)(.*)', re.DOTALL)
    documents = []
    while '<TEXTLONG-OUTLINE>' in text and '</TEXTLONG-OUTLINE>' in text:
        match = pattern.match(text)
        if match:
            before, outline, outline_content, after = match.groups()
            if before:
                documents.extend(markdown(before, renderer=SegmentsRenderer()))
            doc = Document(page_content=outline_content, metadata={"type": 'TEXTLONG-OUTLINE'})
            documents.append(doc)
            text = after
    if text:
        documents.extend(markdown(text, renderer=SegmentsRenderer()))
    return documents
