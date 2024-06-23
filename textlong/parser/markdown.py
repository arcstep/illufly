from typing import Iterable, Dict, Any
import re
import time
import yaml
from mistune import markdown
from mistune.renderers.markdown import MarkdownRenderer
from mistune.core import BlockState
from langchain_core.documents import Document
from ..config import get_default_env

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
            if tok['type'] == 'blank_line':
                md = '\n'
            documents.append(Document(page_content=md, metadata=tok))
        return documents

def parse_markdown(text, start_tag=None, end_tag=None):
    """
    你可以修改 start_tag/end_tag, 使用 <<<< ... >>>> 或 {{ ... }} 等其他方案来标记提纲内容，
    默认为 <OUTLINE> ... </OUTLINE> 的形式。
    """
    start_tag = start_tag or get_default_env("TEXTLONG_OUTLINE_START")
    end_tag = end_tag or get_default_env("TEXTLONG_OUTLINE_END")
    doc_id_generator = get_document_id()
    pattern = re.compile(r'(.*?)(%s.*?%s)(.*)' % (re.escape(start_tag), re.escape(end_tag)), re.DOTALL)
    yaml_pattern = re.compile(r'\n*---+\n(.*?)\n---+\n', re.DOTALL)
    documents = []

    # 提取 YAML Front Matter
    yaml_match = yaml_pattern.match(text)
    if yaml_match:
        yaml_front_matter = yaml_match.group(1)
        metadata = yaml.safe_load(yaml_front_matter)
        doc_id = next(doc_id_generator)
        metadata.update({"id": doc_id, "type": "front_matter"})
        doc = Document(page_content='', metadata=metadata)
        documents.append(doc)
        text = text[yaml_match.end():]

    while start_tag in text and end_tag in text:
        match = pattern.match(text)
        if match:
            before, outline_content, after = match.groups()
            if before:
                documents.extend(markdown(before, renderer=SegmentsRenderer(doc_id_generator)))
            doc_id = next(doc_id_generator)
            doc = Document(page_content=outline_content+"\n\n", metadata={"id": doc_id, "type": 'OUTLINE'})
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