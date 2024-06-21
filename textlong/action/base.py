import os
import copy
from typing import Union, List, Dict, Any
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose

from .documents import MarkdownDocuments
from ..parser import parse_markdown
from ..hub import load_prompt
from ..importer import load_markdown
from ..utils import extract_text

def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, input, is_fake: bool=False, verbose: bool=False):
    if get_verbose() or is_fake or verbose:
        # 用蓝色表示提示语模板
        print("\033[34m" + chain.get_prompts()[0].format(**input) + "\033[0m")

    if is_fake:
        yield '<<<<< is_fake Content >>>>>\n'
    else:
        for chunk in chain.stream(input):
            yield chunk.content

def gather_docs(input: Union[str, List[str]]):
    """
    从input收集文本，有三种情况：
    - input直接提供文本
    - input提供了一个可以读取的文件
    - input是一组可读取的文件
    """

    md = ''

    if isinstance(input, str):
        if input.endswith(".md") and os.path.exists(input):
            input = [input]
        else:
            md = input

    if isinstance(input, list):
        for path in input:
            if isinstance(path, str) and path.endswith(".md") and os.path.exists(path):
                d = load_markdown(path)
                md += "\n\n" + d.markdown
            else:
                raise ValueError(f"Input File Not Exist: {path}")

    return md

def write(
    llm: Runnable,
    task: str=None,
    input: Union[str, List[str]]=None,
    sep_mode: str='all',
    replace: bool=True,
    knowledge: Union[str, List[str]]=None,
    prompt_id: str=None,
    config: Dict[str, Any]=None,
    is_fake: bool=False,
    verbose: bool=False,
    **kwargs
):
    """
    创作长文。
    """
    config = config or {}

    # input
    input_doc = gather_docs(input)
    task_mode, task_todos, old_docs = 'all', [], []
    if input_doc:
        old_docs = MarkdownDocuments(input_doc)
        task_mode, task_todos = old_docs.get_todo_documents(sep_mode)

    # knowledge
    kg_doc = '\n'.join([gather_docs(knowledge)]) if knowledge else ''

    # prompt
    template_folder = config[template_folder] if 'template_folder' in config else None
    prompt = load_prompt(prompt_id or "IDEA", template_folder=template_folder)

    if task_mode == 'all':
        _kwargs = {
            "knowledge__": kg_doc,
            "todo_doc__": '\n'.join([d.page_content for d in task_todos]),
            **kwargs
        }
        chain = _create_chain(llm, prompt, **_kwargs)
        
        resp_md = ""
        for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
            resp_md += delta
            yield ('log', delta)
        yield ('final', resp_md)

    elif task_mode == 'document':
        last_index = None
        new_docs = copy.deepcopy(old_docs)
        for doc, index in task_todos:
            if last_index != None:
                yield ('final', "\n")
            yield ('final', MarkdownDocuments.to_markdown(old_docs.documents[last_index:index]))
            last_index = index + 1

            _kwargs = {
                "knowledge__": kg_doc,
                "todo_doc__": doc.page_content,
                "prev_doc__": MarkdownDocuments.to_markdown(new_docs.get_prev_documents(doc)),
                "next_doc__": MarkdownDocuments.to_markdown(new_docs.get_next_documents(doc)),
                **kwargs
            }
            chain = _create_chain(llm, prompt, **_kwargs)

            resp_md = ""
            for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
                yield ('log', delta)
                resp_md += delta
            yield ('extract', extract_text(resp_md))
            reply_docs = parse_markdown(extract_text(resp_md))
            new_docs.replace_documents(doc, doc, reply_docs)

        yield ('final', MarkdownDocuments.to_markdown(old_docs.documents[last_index:None]))

def stream_log(llm: Runnable, **kwargs):
    """
    打印流式日志。
    
    接收的流式内容都为形如 (mode, content) 的元组，其中：
    mode - 值为 final, extract 或 log
    content - 文本内容
    
    log: 流式输出的中间结果，应当与final或extract搭配使用
    final: 原始的文本结果直接被采纳
    extract: 原始的文本结果经过脱壳后被采纳，例如在扩写过程中脱去可能存在的 <OUTLINE></OUTLINE>外壳
    """
    md = ''
    for mode, chunk in write(llm, **kwargs):
        if mode == 'final':
            md += chunk
            print(chunk, end="")
        elif mode == 'extract':
            md += extract_text(chunk)
        else:
            print(chunk, end="")
    return md

def idea(
    llm: Runnable,
    task: str,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "IDEA"
    return stream_log(llm, task=task, sep_mode=sep_mode, prompt_id=prompt_id, **kwargs)

def outline(
    llm: Runnable,
    task: str,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "OUTLINE"
    return stream_log(llm, task=task, sep_mode=sep_mode, prompt_id=prompt_id, **kwargs)

def from_outline(
    llm: Runnable,
    input: Union[str, List[str]],
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "outline"
    prompt_id = prompt_id or "OUTLINE_DETAIL"
    md = ''
    return stream_log(llm, sep_mode=sep_mode, input=input, prompt_id=prompt_id, **kwargs)
