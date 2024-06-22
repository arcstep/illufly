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
from ..utils import extract_text, color_code

def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, input, is_fake: bool=False, verbose: bool=False, verbose_color: str=None):
    if get_verbose() or is_fake or verbose:
        # 用蓝色表示提示语模板
        print(color_code(verbose_color or '蓝色') + chain.get_prompts()[0].format(**input) + "\033[0m")

    if is_fake:
        yield "FAKE-CONTENT...\n"
    else:
        for chunk in chain.stream(input):
            yield chunk.content

def gather_docs(input: Union[str, List[str]]) -> List[str]:
    """
    从input收集文本，有三种情况：
    - 文本字符串
    - 一个包含文本的文件，一般为md格式
    - 一组包含文本的文件，一般为md格式
    
    TODO: 支持 word、html 等其他格式
    """

    mds = []

    if isinstance(input, str):
        input = [input]

    if isinstance(input, list):
        for s in input:
            if isinstance(s, str) and path.endswith(".md") and os.path.exists(s):
                d = load_markdown(s)
                mds.add(d.markdown)
            else:
                mds.add(s)

    return mds

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
    verbose_color: str=None,
    **kwargs
):
    """
    创作长文。
    
    TODO: 支持更多任务拆分模式
    """
    config = config or {}
    prev_k = config.get('prev_k', 800)
    next_k = config.get('next_k', 200)
    template_folder = config.get('template_folder', None)
    prompt_id = prompt_id or 'IDEA'

    # input
    input_list = gather_docs(input) or ['']
    task_mode, task_todos, old_docs = 'all', [], []

    # knowledge
    kg_doc = '\n'.join([gather_docs(knowledge)]) if knowledge else ''

    # prompt
    prompt = load_prompt(prompt_id, template_folder=template_folder)

    for input_doc, index in enumerate(input_list):
        if input_doc:
            old_docs = MarkdownDocuments(input_doc)
            task_mode, task_todos = old_docs.get_todo_documents(sep_mode)

        if task_mode == 'all':

            _kwargs = {
                "knowledge__": kg_doc,
                "todo_doc__": '\n'.join([d.page_content for d in task_todos]),
                **kwargs
            }
            chain = _create_chain(llm, prompt, **_kwargs)
            
            resp_md = ""
            for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose, verbose_color):
                resp_md += delta
                yield (index, 'log', delta)
            yield (index, 'collect', resp_md)

        elif task_mode == 'document':
            last_index = None
            new_docs = copy.deepcopy(old_docs)
            for doc, index in task_todos:
                if last_index != None:
                    yield (index, 'output', "\n")
                if old_docs.documents[last_index:index]:
                    yield (index, 'output', MarkdownDocuments.to_markdown(old_docs.documents[last_index:index]))
                last_index = index + 1
                
                if doc.page_content and doc.page_content.strip():
                    _kwargs = {
                        "knowledge__": kg_doc,
                        "todo_doc__": doc.page_content,
                        "prev_doc__": MarkdownDocuments.to_markdown(new_docs.get_prev_documents(doc, prev_k)),
                        "next_doc__": MarkdownDocuments.to_markdown(new_docs.get_next_documents(doc, next_k)),
                        **kwargs
                    }
                    chain = _create_chain(llm, prompt, **_kwargs)

                    resp_md = ""
                    for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose, verbose_color):
                        yield (index, 'log', delta)
                        resp_md += delta
                    yield (index, 'extract', extract_text(resp_md))
                    reply_docs = parse_markdown(extract_text(resp_md))
                    new_docs.replace_documents(doc, doc, reply_docs)

                else:
                    # 如果内容是空行就不再处理
                    yield (index, 'log', '(无需处理的空行)')
                    yield (index, 'output', doc.page_content)

            if old_docs.documents[last_index:None]:
                yield (index, 'output', MarkdownDocuments.to_markdown(old_docs.documents[last_index:None]))

def collect_stream(
    llm: Runnable,
    start_marker: str=None,
    end_marker: str=None,
    verbose_color=None,
    output_color=None,
    log_color=None,
    **kwargs
):
    """
    打印流式日志。

    接收的流式内容都为形如 (mode, content) 的元组，其中：
    mode - 值为 output, collect, extract 或 log
    content - 文本内容

    log: 流式输出的中间结果，一般与collect或extract搭配使用
    output: 原始的文本结果直接被采纳
    collect: 流式过程的最终结果收集，过程信息在log中分次输出
    extract: 与collect类似，但最终结果做脱壳处理，例如在扩写过程中脱去可能存在的 <OUTLINE></OUTLINE>外壳
    """
    md = ''
    for index, mode, chunk in write(llm, verbose_color=verbose_color, **kwargs):
        if mode == 'output':
            md += chunk
            print(color_code(output_color or '黄色') + chunk + "\033[0m", end="")
        elif mode == 'collect':
            md += chunk
        elif mode == 'extract':
            md += extract_text(chunk, start_marker, end_marker)
        else:
            print(color_code(log_color or '绿色') + chunk + "\033[0m", end="")
    return md

def idea(
    llm: Runnable,
    task: str,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "IDEA"
    return collect_stream(llm, task=task, sep_mode=sep_mode, prompt_id=prompt_id, **kwargs)

def outline(
    llm: Runnable,
    task: str,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "OUTLINE"
    return collect_stream(llm, task=task, sep_mode=sep_mode, prompt_id=prompt_id, **kwargs)

def from_outline(
    llm: Runnable,
    input: Union[str, List[str]],
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "outline"
    prompt_id = prompt_id or "FROM_OUTLINE"
    return collect_stream(llm, "<OUTLINE>", "</OUTLINE>", sep_mode=sep_mode, input=input, prompt_id=prompt_id, **kwargs)

def outline_from_outline(
    llm: Runnable,
    input: Union[str, List[str]],
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "outline"
    prompt_id = prompt_id or "OUTLINE_FROM_OUTLINE"
    return collect_stream(llm, "<OUTLINE-MORE>", "</OUTLINE-MORE>", sep_mode=sep_mode, input=input, prompt_id=prompt_id, **kwargs)
