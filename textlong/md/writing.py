from typing import Union, List
from abc import ABC, abstractclassmethod
import copy
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import IntelliDocuments
from .prompt import (
    # 基本写作
    PROMPT_BASE_WRITING,
    # 提纲
    PROMPT_OUTLINE_WRITING,
    PROMPT_OUTLINE_REWRITING,
    # 扩写
    PROMPT_DETAIL_WRITING,
    PROMPT_DETAIL_REWRITING,
    # 提取大纲
    PROMPT_FETCH_OUTLINE,
    PROMPT_REFETCH_OUTLINE,
    # 翻译
    PROMPT_TRANSLATE,
    PROMPT_RE_TRANSLATE,
    # 对技术方案摘要
    PROMPT_TECH_SUMMARISE,
)
from .output_parser import MarkdownOutputParser
from ..parser import parse_markdown
from ..hub import load_prompt

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

    def write(self, task: str, prompt_name: str=None, example: str=None):
        """
        创作提纲。
        - task 主题和创作要求
        """
        prompt = load_prompt(prompt_name or "_PROMPT_WRITING_BASE")
        example = example or "你的markdown输出"

        chain = create_chain(self.llm, prompt)

        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs.documents
    
    def rewrite(self, task: str=None, index_doc: Union[str, Document]=None, prompt_name: str=None):
        """
        局部重写。
        - task 补充的修改意见
        - index_doc 要修改的文档
        """
        prompt = load_prompt(prompt_name or "_PROMPT_WRITING_BASE_RE")
        relevant = self.todo_docs.get_relevant_documents(index_doc)
        chain = create_chain(
            self.llm,
            prompt,
            relevant="".join([d.page_content for d in relevant]),
            to_rewrite=index_doc.page_content
        )

        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.replace_documents(index_doc, docs=resp_md)

        return self.todo_docs.documents
    
    def check_rewrite_title(self, title):
        if title and self.last_rewrite_title:
            raise ValueError("title can't be None !")
        if title:
            self.last_rewrite_title = title

    def get_todo_documents(self, title):
        docs = self.todo_docs.get_documents(title)
        if not docs:
            raise ValueError("No title match in documents !")
        return docs

class Outline(BaseWriting):
    """创作提纲。"""

    def write(self, task: str, prompt_name: str=None, example: str=None):
        return super().write(task, prompt_name or "_PROMPT_OUTLINE_WRITING")

    def rewrite(self, task: str=None, index_doc: Union[str, Document]=None, prompt_name: str=None):
        return super().rewrite(task, index_doc, prompt_name or "_PROMPT_OUTLINE_WRITING")

class Detail(BaseWriting):
    """
    根据提纲扩写。
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
    
    def write(self, task: str=None):
        task_howto = f"{task or ''}\n请根据提纲要求完成续写。标题和要求为："
        prompt = load_prompt("_PROMPT_DETAIL_WRITING")
        return self._write(prompt, task_howto)

    def _write(self, prompt_str: str, howto: str):
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")

        task_nodes = self.source_docs.get_outline_task()

        # 批量扩写任务
        for node in task_nodes:
            rel_docs = "".join([d.page_content for d in self.todo_docs.get_relevant_documents(node)])
            chain = create_chain(self.llm, prompt_str, relevant=rel_docs, to_write=node.page_content)

            resp_md = call_markdown_chain(chain, {"task": f"{howto}\n{node.page_content}"})
            reply_docs = parse_markdown(resp_md)
            self.todo_docs.replace_documents(index_doc=node, docs=reply_docs)

        return self.todo_docs.documents
    
    def rewrite(self, task: str=None, index_doc: Union[str, Document]=None, prompt_name: str=None):
        task_howto = f" {task or ''}\n只重写上次续写的这部份。"
        prompt = load_prompt("_PROMPT_DETAIL_WRITING_RE")
        return self._rewrite(
            index_doc=index_doc,
            prompt_str=PROMPT_DETAIL_REWRITING,
            howto=task_howto,
            action="detail"
        )

    def _rewrite(self, title: str, prompt_str: str, howto: str):
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")

        self.check_rewrite_title(title)
        task_title = self.last_rewrite_title

        docs = self.get_todo_documents(task_title)
        md_existing = IntelliDocuments.get_markdown(docs)
        outline_relv = IntelliDocuments.get_markdown(
            self.source_docs.get_relevant_documents(task_title)
        )
        detail_prev = IntelliDocuments.get_markdown(
            self.todo_docs.get_prev_documents(task_title)
        )

        chain = create_chain(
            self.llm,
            prompt_str,
            outline=outline_relv,
            detail=detail_prev,
            to_rewrite=md_existing
        )

        resp_md = call_markdown_chain(chain, {"task": howto})
        reply_docs = IntelliDocuments.parse_markdown(resp_md)
        self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)
        
        # 将新内容的标题作为重写标题
        self.last_rewrite_title = reply_docs[0].page_content

        return reply_docs

class Fetch(Detail):
    """
    提取大纲。
    - 从 self.source_docs 中提取大纲到 self.todo_docs
    """

    def write(self, task: str=None):
        task_howto = f"{task or ''}\n请根据文字内容提取大纲。要提取的内容为："
        return self._write(
            prompt_str=PROMPT_FETCH_OUTLINE,
            howto=task_howto,
            action="fetch"
        )

    def rewrite(self, task: str=None, title: str=None):
        task_howto = f" {task or ''}\n只重新提取这部份的提纲。"
        return self._rewrite(
            title=title,
            prompt_str=PROMPT_REFETCH_OUTLINE,
            howto=task_howto,
            action="fetch"
        )

class Translate(Detail):
    """
    翻译。
    - self.source_docs 中翻译到 self.todo_docs
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        IntelliDocuments.update_action(self.documents, "origin")

    def write(self, task: str=None):
        task_howto = f"{task or '从中文翻译为英文'}\n请根据已有文字翻译内容提取大纲。要翻译的内容为："
        return self._write(
            prompt_str=PROMPT_TRANSLATE,
            howto=task_howto,
            action="translate"
        )

    def rewrite(self, task: str=None, title: str=None):
        task_howto = f" {task or '从中文翻译为英文'}\n只重新翻译这部份内容。"
        return self._rewrite(
            title=title,
            prompt_str=PROMPT_RE_TRANSLATE,
            howto=task_howto,
            action="translate"
        )

class Summarise(Detail):
    """
    摘要任务。
    """

    def write(self, task: str=None):
        """
        提取摘要。
        - task 主题和创作要求
        """

        chain = create_chain(
            self.llm,
            PROMPT_TECH_SUMMARISE
        )

        info = self.source_docs.markdown
        resp_md = call_markdown_chain(chain, {"task": task or "按要求做摘要。", "info": info})
        
        self.todo_docs.documents = []
        self.todo_docs.import_markdown(resp_md, action="summarise")

        return self.todo_docs.documents
