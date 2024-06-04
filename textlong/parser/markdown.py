from typing import Iterable, Dict, Any
import re
from mistune import markdown
from mistune.renderers.markdown import MarkdownRenderer
from mistune.core import BlockState
from langchain_core.documents import Document

class SegmentsRenderer(MarkdownRenderer):
    def create_document(self, content, type, attrs=None):
        if '<TEXTLONG-OUTLINE>' in content and '</TEXTLONG-OUTLINE>' in content:
            outline_content = re.search('<TEXTLONG-OUTLINE>(.*?)</TEXTLONG-OUTLINE>', content, re.DOTALL).group(1)
            doc = Document(page_content=outline_content, metadata={"type": 'TEXTLONG-OUTLINE'})
            yield doc
            content = content.replace(f'<TEXTLONG-OUTLINE>{outline_content}</TEXTLONG-OUTLINE>', '')
            # Split the remaining content into two parts
            content_parts = content.split('\n', 1)
            for part in content_parts:
                if part:
                    doc = Document(page_content=part, metadata={"type": type, "attrs": attrs})
                    yield doc
        elif content:
            doc = Document(page_content=content, metadata={"type": type, "attrs": attrs})
            yield doc

    def __call__(self, tokens: Iterable[Dict[str, Any]], state: BlockState) -> str:
        documents = []
        out = ""
        for tok in tokens:
            if tok['type'] in ['heading', 'block_code', 'image']:
                documents.extend(self.create_document(out, 'text'))
                out = self.render_token(tok, state)
                documents.extend(self.create_document(out, tok['type'], tok['attrs']))
                out = ""
            else:
                out += self.render_token(tok, state)
        documents.extend(self.create_document(out, 'text'))
        return documents

def parse_markdown(text):
    return markdown(text, renderer=SegmentsRenderer())