import copy
from typing import Union, List
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import IntelliDocuments
from .output_parser import MarkdownOutputParser
from ..parser import parse_markdown
from ..hub import load_prompt
from ..utils import markdown


def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, input):
    if get_verbose():
        print("\033[34m" + "#"*20, "PROMPT BEGIN", "#"*20)  # 蓝色
        print(chain.get_prompts()[0].format(**input))
        print("#"*20, "PROMPT END ", "#"*20 + "\033[0m")  # 重置颜色

    buffer = ""
    start_index = -1
    for chunk in chain.stream(input):
        buffer += chunk.content
        if start_index == -1:
            start_index = buffer.find('>->>>')
            if start_index != -1:
                yield buffer[start_index+5:]
                buffer = ""
        else:
            if any([buffer.endswith(s) for s in ['<', '<<', '<<<', '<<<-']]):
                if buffer.endswith('<<<-<'):
                    yield buffer[:-5]
                    break
                else:
                    continue
            if buffer.find('<<<-<') !=-1:
                yield buffer[:-5]
                break
            else:
                yield buffer
                buffer = ""

def idea(task: str, llm: Runnable, template_id: str=None, ref_doc: str=None):
    """
    创意
    """
    prompt = load_prompt(template_id or "IDEA")
    doc = f'你已经完成的创作如下：\n{ref_doc}' if ref_doc != None else ''
    chain = _create_chain(llm, prompt, todo_doc=doc)

    for delta in _call_markdown_chain(chain, {"task": task}):
        yield delta

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

    last_index = None
    outline_docs = copy.deepcopy(todo_docs.documents)
    for doc, index in todo_docs.get_outline_task():
        # 生成<OUTLINE/>之前的部份
        if last_index != None:
            yield "\n"
        yield markdown(outline_docs[last_index:index])
        last_index = index + 1

        # 生成匹配的<OUTLINE/>所在的部份
        prev_doc = markdown(todo_docs.get_prev_documents(doc))
        next_doc = markdown(todo_docs.get_next_documents(doc))
        chain = _create_chain(
            llm,
            prompt,
            prev_doc=prev_doc,
            next_doc=next_doc,
            todo_doc=f'>->>>\n{doc.page_content}<<<-<\n\n'
        )

        task_howto = f"请仅针对上述`>->>>`和`<<<-<`包围的部份扩写。{task or ''}"
        resp_md = ""
        for delta in _call_markdown_chain(chain, {"task": task_howto}):
            yield delta
            resp_md += delta
        reply_docs = parse_markdown(resp_md)
        todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

    # 生成最后一个<OUTLINE/>之后的部份
    yield markdown(outline_docs[last_index:None])


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
    chain = _create_chain(llm, prompt, todo_doc=ref_doc)
    resp_md = _call_markdown_chain(chain, {"task": task})
    for chunk in resp_md:
        yield chunk

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
            todo_doc = f'>->>>\n{md}\n<<<-<'
            prev_doc = markdown(ref_docs.get_prev_documents(docs[0]))
            chain = _create_chain(llm, prompt, prev_doc=prev_doc, todo_doc=todo_doc)
            for chunk in _call_markdown_chain(chain, {"task": task or ''}):
                yield chunk
        else:
            yield ""

    for doc in ref_docs.documents:
        md_len += len(doc.page_content)
        task_docs.append(doc)
        if md_len <= k:
            continue

        for delta in create_md(task_docs):
            yield delta
        md_len = 0
        task_docs = []

    if task_docs:
        for delta in create_md(task_docs):
            yield delta

def translate(ref_doc: str, llm: Runnable, template_id: str=None, task: str=None, k: int=1000):
    """
    翻译
    """
    _template_id = template_id or "TRANSLATE"
    _task = task or "如果原文为英文，就翻译为中文；如果原文为中文，就翻译为英文。"
    return rewrite(ref_doc, llm, _template_id, _task, k)
