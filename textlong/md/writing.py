import copy
from typing import Union, List
from langchain_core.runnables import Runnable
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
        print("\033[34m" + "#"*20, "PROMPT BEGIN", "#"*20)  # 蓝色
        print(chain.get_prompts()[0].format(**input))
        print("#"*20, "PROMPT END ", "#"*20 + "\033[0m")  # 重置颜色

    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")

    print("\033[32m" + f"\n\n生成{len(text)}字。" + "\033[0m")  # 绿色
    return MarkdownOutputParser().invoke(text)[0]

def idea(task: str, llm: Runnable, template_id: str=None, ref_doc: str=None):
    """
    创意
    """
    prompt = load_prompt(template_id or "IDEA")
    doc = f'你已经完成的创作如下：\n{ref_doc}' if ref_doc != None else ''
    chain = create_chain(llm, prompt, todo_doc=doc)
    resp_md = call_markdown_chain(chain, {"task": task})

    return resp_md

def outline(task: str, llm: Runnable, template_id: str=None, ref_doc: str=None):
    """
    提纲
    """
    _template_id = template_id or "OUTLINE"
    return idea(task=task, llm=llm, template_id=_template_id, ref_doc=ref_doc)

def outline_detail(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None):
    """
    扩写
    """
    todo_docs = IntelliDocuments(ref_doc)
    prompt = load_prompt(template_id or "OUTLINE_DETAIL")

    for doc in todo_docs.get_outline_task():
        prev_doc = markdown(todo_docs.get_prev_documents(doc))
        next_doc = markdown(todo_docs.get_next_documents(doc))
        chain = create_chain(
            llm,
            prompt,
            prev_doc=prev_doc,
            next_doc=next_doc,
            todo_doc=f'>->>>\n{doc.page_content}<-<<<\n\n'
        )

        task_howto = f"请仅针对上述`>->>>`和`<-<<<`包围的部份扩写。{task or ''}"
        resp_md = call_markdown_chain(chain, {"task": task_howto})
        reply_docs = parse_markdown(resp_md)
        todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

    return todo_docs.markdown

def outline_self(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None):
    """
    丰富提纲
    """
    _template_id = template_id or "OUTLINE_SELF"
    return outline_detail(ref_doc, llm, _template_id, task)

def fetch(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None, k: int=1000):
    """
    提取

    - 按任务意图提取文档
    - 默认提取`摘要`，可以通过`task`指定知识三元组、人物、工作流程等具体要求
    """

    prompt = load_prompt(template_id or "SUMMARISE")
    chain = create_chain(llm, prompt, todo_doc=ref_doc)
    resp_md = call_markdown_chain(chain, {"task": task})
    return resp_md

def rewrite(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None, k: int=1000):
    """
    修改

    - 按修改意图和滚动上下文窗口修改长文档，例如替换文中的产品名称
    """
    ref_docs = IntelliDocuments(ref_doc)
    prompt = load_prompt(template_id or "REWRITE")

    resp_md = ""
    task_docs = []
    md_len = 0
    
    def create_md(docs):
        md = markdown(docs)
        if len(md):
            todo_doc = f'>->>>\n{md}\n<-<<<'
            prev_doc = markdown(ref_docs.get_prev_documents(docs[0]))
            chain = create_chain(llm, prompt, prev_doc=prev_doc, todo_doc=todo_doc)
            task_howto = f"请针对`>->>>`和`<-<<<`包围的部份重写。{task or ''}"
            return call_markdown_chain(chain, {"task": task_howto})
        else:
            return ""

    for doc in ref_docs.documents:
        md_len += len(doc.page_content)
        task_docs.append(doc)
        if md_len <= k:
            continue

        resp_md += create_md(task_docs) + "\n\n"
        md_len = 0
        task_docs = []

    if task_docs:
        resp_md += create_md(task_docs)

    return resp_md

def translate(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None, k: int=1000):
    """
    翻译
    """
    _template_id = template_id or "TRANSLATE"
    _task = task or "如果原文为英文，就翻译为中文；如果原文为中文，就翻译为英文。"
    return refine(ref_doc, llm, _template_id, _task, k)
