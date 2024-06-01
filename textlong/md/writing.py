from typing import Union, List
from abc import ABC, abstractclassmethod
import copy

from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import IntelliDocuments
from .prompt import (
    PROMPT_OUTLINE_WRITING,
    PROMPT_OUTLINE_REWRITING,
    PROMPT_DETAIL_WRITING,
    PROMPT_DETAIL_REWRITING,
    PROMPT_FETCH_OUTLINE,
)
from .output_parser import MarkdownOutputParser

def create_chain(llm, prompt_template, **kwargs):
    prompt = PromptTemplate.from_template(prompt_template).partial(**kwargs)
    return prompt | llm

def call_markdown_chain(chain, input):
    
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
    写作任务。
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
        return IntelliDocuments.get_markdown(self.documents)

    @abstractclassmethod
    def write(self, task: str):
        """
        创作提纲。
        - task 主题和创作要求
        """
        pass
    
    def rewrite(self, task: str=None, title: str=None):
        """
        局部重写。
        - title 要修改的标题或文字开头部份
        - task 补充的修改意见
        """
        raise NotImplementedError("method `rewrite` not implementd yet.")
    
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
    """提纲。"""

    def write(self, task: str):

        chain = create_chain(
            self.llm,
            PROMPT_OUTLINE_WRITING
        )

        resp_md = call_markdown_chain(chain, {"task": task})
        
        self.todo_docs.documents = []
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs.documents
    
    def rewrite(self, task: str=None, title: str=None):
        
        self.check_rewrite_title(title)
        task_title = self.last_rewrite_title

        docs = self.get_todo_documents(task_title)        
        md_existing = IntelliDocuments.get_markdown(docs)
        chain = create_chain(
            self.llm,
            PROMPT_OUTLINE_REWRITING,
            outline=self.markdown,
            to_rewrite=md_existing
        )

        task_confirm = f" {task or ''}\n只针对明确要求重写的这部份重写。"
        resp_md = call_markdown_chain(chain, {"task": task_confirm})

        reply_docs = IntelliDocuments.parse_markdown(resp_md)
        self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)

        # 将新内容的标题作为重写标题
        self.last_rewrite_title = reply_docs[0].page_content
        
        return reply_docs
    
class Detail(BaseWriting):
    """
    扩写。
    - 将 self.source_docs 作为大纲，扩写到 self.todo_docs
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
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")
        
        task_nodes = self.source_docs.get_leaf_outline()

        # 批量扩写任务
        for node in task_nodes:
            task_title = node.page_content
            outline_relv_docs = IntelliDocuments.get_markdown(
                self.source_docs.get_relevant_documents(task_title)
            )
            detail_prev_docs = IntelliDocuments.get_markdown(
                self.todo_docs.get_prev_documents(task_title)
            )

            chain = create_chain(
                self.llm,
                PROMPT_DETAIL_WRITING,
                outline=outline_relv_docs,
                detail=detail_prev_docs
            )

            task_md = IntelliDocuments.get_markdown(
                self.source_docs.get_documents(task_title)
            )
            task_confirm = f"{task or ''}\n请根据提纲要求完成续写。标题和要求为：\n{task_md}"
            resp_md = call_markdown_chain(chain, {"task": task_confirm})

            reply_docs = IntelliDocuments.parse_markdown(resp_md)
            self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)

        return self.todo_docs.documents

    def rewrite(self, task: str=None, title: str=None):

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
            PROMPT_DETAIL_REWRITING,
            outline=outline_relv,
            detail=detail_prev,
            to_rewrite=md_existing
        )

        task_confirm = f" {task or ''}\n只重写上次续写的这部份。"
        resp_md = call_markdown_chain(chain, {"task": task_confirm})

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
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")
        
        task_nodes = self.source_docs.get_leaf_outline()

        # 批量提取任务
        for node in task_nodes:
            task_title = node.page_content
            outline_relv_docs = IntelliDocuments.get_markdown(
                self.source_docs.get_relevant_documents(task_title)
            )
            detail_prev_docs = IntelliDocuments.get_markdown(
                self.todo_docs.get_prev_documents(task_title)
            )

            chain = create_chain(
                self.llm,
                PROMPT_FETCH_OUTLINE,
                outline=outline_relv_docs,
                detail=detail_prev_docs
            )

            task_md = IntelliDocuments.get_markdown(
                self.source_docs.get_documents(task_title)
            )
            task_confirm = f"{task or ''}\n请根据文字内容提取大纲。要提取的内容为：\n{task_md}"
            resp_md = call_markdown_chain(chain, {"task": task_confirm})

            reply_docs = IntelliDocuments.parse_markdown(resp_md)
            self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)

        return self.todo_docs.documents

    def rewrite(self, task: str=None, title: str=None):

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
            PROMPT_DETAIL_REWRITING,
            outline=outline_relv,
            detail=detail_prev,
            to_rewrite=md_existing
        )

        task_confirm = f" {task or ''}\n只重写上次续写的这部份。"
        resp_md = call_markdown_chain(chain, {"task": task_confirm})

        reply_docs = IntelliDocuments.parse_markdown(resp_md)
        self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)
        
        # 将新内容的标题作为重写标题
        self.last_rewrite_title = reply_docs[0].page_content

        return reply_docs

class Clone(Detail):
    """仿写"""

    def write(self, task: str=None):
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")
        
        task_nodes = self.source_docs.get_leaf_outline()

        # 批量扩写任务
        for node in task_nodes:
            task_title = node.page_content
            outline_relv_docs = IntelliDocuments.get_markdown(
                self.source_docs.get_relevant_documents(task_title)
            )
            detail_prev_docs = IntelliDocuments.get_markdown(
                self.todo_docs.get_prev_documents(task_title)
            )

            chain = create_chain(
                self.llm,
                PROMPT_DETAIL_WRITING,
                outline=outline_relv_docs,
                detail=detail_prev_docs
            )

            task_md = IntelliDocuments.get_markdown(
                self.source_docs.get_documents(task_title)
            )
            task_confirm = f"{task or ''}\n请根据提纲要求完成续写。标题和要求为：\n{task_md}"
            resp_md = call_markdown_chain(chain, {"task": task_confirm})

            reply_docs = IntelliDocuments.parse_markdown(resp_md)
            self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)

        return self.todo_docs.documents

    def rewrite(self, task: str=None, title: str=None):

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
            PROMPT_DETAIL_REWRITING,
            outline=outline_relv,
            detail=detail_prev,
            to_rewrite=md_existing
        )

        task_confirm = f" {task or ''}\n只重写上次续写的这部份。"
        resp_md = call_markdown_chain(chain, {"task": task_confirm})

        reply_docs = IntelliDocuments.parse_markdown(resp_md)
        self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)
        
        # 将新内容的标题作为重写标题
        self.last_rewrite_title = reply_docs[0].page_content

        return reply_docs

class Translate(Detail):
    """翻译"""

    def write(self, task: str=None):
        if not self.source_docs.documents:
            raise ValueError("MUST contain some documents from source!")
        
        task_nodes = self.source_docs.get_leaf_outline()

        # 批量扩写任务
        for node in task_nodes:
            task_title = node.page_content
            outline_relv_docs = IntelliDocuments.get_markdown(
                self.source_docs.get_relevant_documents(task_title)
            )
            detail_prev_docs = IntelliDocuments.get_markdown(
                self.todo_docs.get_prev_documents(task_title)
            )

            chain = create_chain(
                self.llm,
                PROMPT_DETAIL_WRITING,
                outline=outline_relv_docs,
                detail=detail_prev_docs
            )

            task_md = IntelliDocuments.get_markdown(
                self.source_docs.get_documents(task_title)
            )
            task_confirm = f"{task or ''}\n请根据提纲要求完成续写。标题和要求为：\n{task_md}"
            resp_md = call_markdown_chain(chain, {"task": task_confirm})

            reply_docs = IntelliDocuments.parse_markdown(resp_md)
            self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)

        return self.todo_docs.documents

    def rewrite(self, task: str=None, title: str=None):

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
            PROMPT_DETAIL_REWRITING,
            outline=outline_relv,
            detail=detail_prev,
            to_rewrite=md_existing
        )

        task_confirm = f" {task or ''}\n只重写上次续写的这部份。"
        resp_md = call_markdown_chain(chain, {"task": task_confirm})

        reply_docs = IntelliDocuments.parse_markdown(resp_md)
        self.todo_docs.replace_documents(new_docs=reply_docs, title=task_title)
        
        # 将新内容的标题作为重写标题
        self.last_rewrite_title = reply_docs[0].page_content

        return reply_docs