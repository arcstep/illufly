from typing import Iterable, Dict, Any, List, Union, Tuple
import re
import time
import random
import yaml
import copy
from mistune import markdown
from mistune.renderers.markdown import MarkdownRenderer
from mistune.core import BlockState
from .....document import Document
from ......config import get_env

class SegmentsRenderer(MarkdownRenderer):
    def __init__(self, doc_id_generator, source: str=None):
        super().__init__()
        self.doc_id_generator = doc_id_generator
        self.source = source or 'unknown'

    def __call__(self, tokens: Iterable[Dict[str, Any]], state: BlockState) -> str:
        documents = []
        for tok in tokens:
            md = self.render_token(tok, state)
            doc_id = next(self.doc_id_generator)
            tok.update({"id": doc_id, "source": self.source})
            if tok['type'] == 'blank_line':
                md = '\n'
            documents.append(Document(text=md, meta=tok))
        return documents

def create_front_matter(dict_data: Dict[str, Any]):
    """
    构造 YAML Front Matter
    """
    if isinstance(dict_data, dict):
        meta = copy.deepcopy(dict_data)
        for e_tag in ['id', 'type']:
            if e_tag in meta:
                meta.pop(e_tag, None)
        for e_tag in ['verbose', 'is_fake']:
            tags = meta.get('args', {})
            if e_tag in tags:
                tags.pop(e_tag, None)
        yaml_str = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        return "---\n" + yaml_str.replace("\n\n", "\n") + "---\n\n"
    else:
        return ''

def fetch_front_matter(text: str):
    """
    提取 YAML Front Matter
    """
    yaml_pattern = re.compile(r'\n*---+\n(.*?)\n---+\n', re.DOTALL)
    yaml_match = yaml_pattern.match(text)
    if yaml_match:
        yaml_front_matter = yaml_match.group(1)
        meta = yaml.safe_load(yaml_front_matter)
        return meta, text[yaml_match.end():]
    else:
        return {}, text

def parse_markdown(text: str, start_tag: str=None, end_tag: str=None, source: str=None):
    """
    你可以修改 start_tag/end_tag, 使用 <<<< ... >>>> 或 {{ ... }} 等其他方案来标记提纲内容，
    默认为 <OUTLINE> ... </OUTLINE> 的形式。
    """
    start_tag = start_tag or get_env("ILLUFLY_OUTLINE_START")
    end_tag = end_tag or get_env("ILLUFLY_OUTLINE_END")
    doc_id_generator = create_document_id()
    pattern = re.compile(r'(.*?)(%s.*?%s)(.*)' % (re.escape(start_tag), re.escape(end_tag)), re.DOTALL)
    documents = []

    # 提取 YAML Front Matter
    meta, text = fetch_front_matter(text)
    if meta:
        doc_id = next(doc_id_generator)
        meta.update({"id": doc_id, "type": "front_matter", "source": source})
        doc = Document(text='', meta=meta)
        documents.append(doc)

    # 从文本中提取标记内的内容
    while start_tag in text and end_tag in text:
        match = pattern.match(text)
        if match:
            before, outline_content, after = match.groups()
            if before:
                documents.extend(markdown(before, renderer=SegmentsRenderer(doc_id_generator, source)))
            doc_id = next(doc_id_generator)
            doc = Document(text=outline_content+"\n\n", meta={"id": doc_id, "type": 'OUTLINE', "source": source})
            documents.append(doc)
            text = after
    if text:
        documents.extend(markdown(text, renderer=SegmentsRenderer(doc_id_generator, source)))
    return documents

def create_document_id():
    counter = 0
    while True:
        timestamp = str(int(time.time()))[-4:]
        random_number = f'{random.randint(0, 999):03}'
        counter_str = f'{counter:03}'
        yield f'{timestamp}-{random_number}-{counter_str}'
        counter = 0 if counter == 999 else counter + 1

def list_markdown(documents: Union[List[Document], List[Tuple[Document, int]]]):
    if len(documents) > 0:
        if isinstance(documents[0], Document):
            docs = documents
        elif isinstance(documents[0], tuple):
            docs = [d for d, index in documents]
        else:
            docs = []
    return [(d.meta['type'][:2] + "-" + d.meta['id'][-7:], d.text) for d in docs if d]
