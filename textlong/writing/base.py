import copy
from typing import Union, List
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder

from .documents import MarkdownDocuments
from .output_parser import MarkdownOutputParser
from ..parser import parse_markdown
from ..hub import load_string_prompt
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

def gather_knowledge(knowledge: List[str]):
    kg_doc = ''
    if knowledge:
        if isinstance(knowledge, str):
            knowledge = [knowledge]
        kg_doc = '你应当知道这些知识：'
        kg_doc += '\n'.join([d for d in knowledge])
    return kg_doc

def from_idea(llm: Runnable, task: str=None, prompt_id: str=None, input_doc: str=None, knowledge: List[str]=None, **kwargs):
    """
    创意：从一个创意开始生成长文档。
    """
    if not task:
        raise ValueError("'task' MUST NOT BE EMPTY !")

    prompt = load_string_prompt("from_idea", prompt_id or "IDEA")
    todo_doc = f'你已经完成的创作如下：\n{input_doc}' if input_doc != None else ''
    kg = gather_knowledge(knowledge)
    chain = _create_chain(llm, prompt, todo_doc=todo_doc, knowledge=kg, **kwargs)

    for delta in _call_markdown_chain(chain, {"task": task}):
        yield delta

def from_outline(llm: Runnable, input_doc: str=None, prompt_id: str=None, task: str=None, knowledge: List[str]=None, **kwargs):
    """
    扩写：从大纲扩充到细节。
    """
    if not input_doc:
        raise ValueError("'input_doc' MUST NOT BE EMPTY !")

    todo_docs = MarkdownDocuments(input_doc)
    kg = gather_knowledge(knowledge)
    prompt = load_string_prompt("from_outline", prompt_id or "OUTLINE_DETAIL")

    last_index = None
    outline_docs = copy.deepcopy(todo_docs.documents)
    for doc, index in todo_docs.get_outline_task():
        # 生成<OUTLINE/>之前的部份
        if last_index != None:
            yield "\n"
        yield MarkdownDocuments.to_markdown(outline_docs[last_index:index])
        last_index = index + 1

        # 生成匹配的<OUTLINE/>所在的部份
        prev_doc = MarkdownDocuments.to_markdown(todo_docs.get_prev_documents(doc))
        next_doc = MarkdownDocuments.to_markdown(todo_docs.get_next_documents(doc))
        todo_doc = f'{prev_doc}>->>>\n{doc.page_content}<<<-<\n\n{next_doc}'
        chain = _create_chain(llm, prompt, todo_doc=todo_doc, knowledge=kg, **kwargs)

        resp_md = ""
        task_howto = f"请仅针对上述`>->>>`和`<<<-<`包围的部份扩写。{task or ''}"
        for delta in _call_markdown_chain(chain, {"task": task_howto}):
            yield delta
            resp_md += delta
        reply_docs = parse_markdown(resp_md)
        todo_docs.replace_documents(index_doc=doc, docs=reply_docs)

    # 生成最后一个<OUTLINE/>之后的部份
    yield MarkdownDocuments.to_markdown(outline_docs[last_index:None])

def extract(llm: Runnable, input_doc: str=None, prompt_id: str=None, task: str=None, k: int=1000, knowledge: List[str]=None, **kwargs):
    """
    提取：按任务意图从长文档提取内容。

    - 默认提取`摘要`，可以通过`task`指定知识三元组、人物、工作流程等具体要求
    """
    if not input_doc:
        raise ValueError("'input_doc' MUST NOT BE EMPTY !")

    prompt = load_string_prompt("extract", prompt_id or "SUMMARISE")
    kg = gather_knowledge(knowledge)
    chain = _create_chain(llm, prompt, todo_doc=input_doc, knowledge=kg, **kwargs)
    resp_md = _call_markdown_chain(chain, {"task": task})
    for chunk in resp_md:
        yield chunk

def from_chunk(llm: Runnable, input_doc: str=None, prompt_id: str=None, task: str=None, k: int=1000, knowledge: List[str]=None, **kwargs):
    """
    修改：从一个长文档的分段逐个进行处理。

    - 例如，例如替换文中的产品名称
    """
    if not input_doc:
        raise ValueError("'input_doc' MUST NOT BE EMPTY !")

    ref_docs = MarkdownDocuments(input_doc)
    prompt = load_string_prompt("from_chunk", prompt_id or "REWRITE")
    kg = gather_knowledge(knowledge)

    resp_md = ""
    task_docs = []
    md_len = 0
    
    def create_md(docs):
        md = MarkdownDocuments.to_markdown(docs)
        if len(md):
            prev_doc = MarkdownDocuments.to_markdown(ref_docs.get_prev_documents(docs[0]))
            todo_doc = f'{prev_doc}>->>>\n{md}\n<<<-<'
            chain = _create_chain(llm, prompt, todo_doc=todo_doc, knowledge=kg, **kwargs)
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

