import copy
from typing import Union, List
from abc import ABC, abstractclassmethod
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import IntelliDocuments
from .output_parser import MarkdownOutputParser
from ..parser import parse_markdown
from ..hub import load_prompt
from ..utils import markdown

def create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def call_markdown_chain(chain, input):
    if get_verbose():
        print("#"*20, "PROMPT BEGIN", "#"*20)
        print(chain.get_prompts()[0].format(**input))
        print("#"*20, "PROMPT  END ", "#"*20)

    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")

    print(f"\n\n实际字数: {len(text)}")
    return MarkdownOutputParser().invoke(text)[0]

class BaseWriting(ABC):
    """
    基本写作。
    """

    def __init__(self, document: Union[str, IntelliDocuments]=None, llm=None, **kwargs):

        self.llm = llm
        self.last_rewrite_title = None

        docs = IntelliDocuments()
        if isinstance(document, str):
            docs = IntelliDocuments(doc_str=document)
        elif isinstance(document, IntelliDocuments):
            docs = document
        self.todo_docs = docs

    @property
    def documents(self):
        return self.todo_docs.documents

    @property
    def markdown(self):
        return self.todo_docs.markdown

    def write(self, task: str, template_id: str=None):
        """
        创作提纲。
        - task 主题和创作要求
        """
        prompt = load_prompt('write', template_id or "创意")
        chain = create_chain(self.llm, prompt)
        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs.documents
    
    def summarise(self):
        pass
    
    def batch(self):
        pass
    
    def refine(self):
        pass
    
class Outline(BaseWriting):
    """创作提纲。"""

    def write(self, task: str, template_id: str=None):
        return super().write(task, template_id or "提纲")

class BatchWriting(BaseWriting):
    """
    批量任务处理。
    - 根据提纲 source_docs 扩写 todo_docs
    """

    def __init__(self, source: Union[str, IntelliDocuments, BaseWriting], **kwargs):
        super().__init__(**kwargs)
        
        docs = IntelliDocuments()
        if isinstance(source, str):
            docs = IntelliDocuments(doc_str=source)
        elif isinstance(source, BaseWriting):
            docs = copy.deepcopy(source.todo_docs)
            if 'llm' not in kwargs:
                self.llm = source.llm
        elif isinstance(source, IntelliDocuments):
            docs = source
        self.source_docs = docs

        # 如果不是提前加载扩写内容（这种情况通常是从持久化中恢复任务），就从扩写依据的大纲中提取
        if not self.todo_docs.documents:
            self.todo_docs.documents = copy.deepcopy(self.source_docs.documents)

class Detail(BatchWriting):
    """
    批量任务处理。
    - 根据提纲 source_docs 扩写 todo_docs
    """

    def write(self, task: str=None, template_id: str=None):
        task_howto = f"{task or ''}\n请根据提纲要求完成扩写。标题和要求为："
        prompt = load_prompt('batch', template_id or "扩写")
        return self._write(prompt, task_howto)

    def _write(self, prompt: PromptTemplate, howto: str):
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")

        # 批量扩写任务
        for doc in self.source_docs.get_outline_task():
            prev_doc = markdown(self.todo_docs.get_prev_documents(doc))
            next_doc = markdown(self.todo_docs.get_next_documents(doc))
            chain = create_chain(
                self.llm,
                prompt,
                prev_doc=prev_doc,
                next_doc=next_doc,
                to_write=doc.page_content
            )

            resp_md = call_markdown_chain(chain, {"task": f"{howto}\n{doc.page_content}"})
            reply_docs = parse_markdown(resp_md)
            self.todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

        return self.todo_docs.documents
