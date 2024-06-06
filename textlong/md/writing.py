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

class Writing(ABC):
    """
    基本写作。
    """

    def __init__(
        self,
        todo_docs: Union[str, IntelliDocuments]=None,
        ref_docs: Union[str, IntelliDocuments]=None,
        llm=None,
        **kwargs
    ):

        self.llm = llm

        if isinstance(ref_docs, str) or ref_docs == None:
            self.ref_docs = IntelliDocuments(doc_str=ref_docs)
        elif isinstance(ref_docs, IntelliDocuments):
            self.ref_docs = docs
        else:
            raise ValueError("ref_docs MUST be str or IntelliDocuments")
        
        if isinstance(todo_docs, str) or todo_docs == None:
            self.todo_docs = IntelliDocuments(doc_str=todo_docs)
        elif isinstance(todo_docs, IntelliDocuments):
            self.todo_docs = todo_docs
        else:
            raise ValueError("todo_docs MUST be str or IntelliDocuments")

    @property
    def documents(self):
        return self.todo_docs.documents

    @property
    def markdown(self):
        return self.todo_docs.markdown

    def idea(self, task: str, template_id: str=None):
        """创意"""
        prompt = load_prompt(template_id or "创意")
        chain = create_chain(self.llm, prompt)
        resp_md = call_markdown_chain(chain, {"task": task})
        self.todo_docs.import_markdown(resp_md)

        return self.todo_docs.documents
    
    def outline(self, task: str, template_id: str=None):
        """提纲"""
        return self.idea(task, template_id or "提纲")

    def detail(self, task: str=None, template_id: str=None):
        """扩写"""
        if not self.ref_docs.documents:
            raise ValueError("必须提供《参考提纲》作为扩写依据")

        self.todo_docs = copy.deepcopy(self.ref_docs)
        prompt = load_prompt(template_id or "扩写")

        for doc in self.todo_docs.get_outline_task():
            prev_doc = markdown(self.todo_docs.get_prev_documents(doc))
            next_doc = markdown(self.todo_docs.get_next_documents(doc))
            chain = create_chain(
                self.llm,
                prompt,
                prev_doc=prev_doc,
                next_doc=next_doc,
                todo_doc=doc.page_content
            )

            task_howto = f"{task or ''}\n请根据提纲要求完成扩写。标题和要求为：\n{doc.page_content}"
            resp_md = call_markdown_chain(chain, {"task": task_howto})
            reply_docs = parse_markdown(resp_md)
            self.todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

        return self.todo_docs.documents


    def fetch(self, task: str, template_id: str=None):
        return self.idea(task, template_id or "提纲")
    
    def summarise(self):
        pass
    
    def batch(self):
        pass
    
    def refine(self):
        pass

