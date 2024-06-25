import os
import copy
from datetime import datetime
from typing import Union, List, Dict, Any
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose

from .markdown import MarkdownLoader
from .command import Command
from ..parser import parse_markdown, create_front_matter
from ..hub import load_prompt
from ..importer import load_markdown
from ..utils import extract_text, color_code
from ..config import (
    get_text_color,
    get_info_color,
    get_chunk_color,
    get_warn_color,
    get_default_env,
)

def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, input, is_fake: bool=False, verbose: bool=False):
    if get_verbose() or is_fake or verbose:
        yield ('info', get_info_color() + chain.get_prompts()[0].format(**input) + "\033[0m")

    if is_fake:
        yield ('info', "Fake-Output-Content...\n")
    else:
        for chunk in chain.stream(input):
            yield ('chunk', chunk.content)

def gather_docs(input: Union[str, List[str]], base_folder: str="") -> str:
    """
    从input收集文本，有如下情况：
    - 文本字符串
    - 文本字符串列表
    - 一个包含文本的文件，一般为md格式
    - 一组包含文本的文件，一般为md格式
    
    TODO: 支持 word、html 等其他格式
    """

    mds = []

    if isinstance(input, str):
        input = [input]

    if isinstance(input, list):
        for s in input:
            if isinstance(s, str) and s.endswith(".md"):
                path = os.path.join(base_folder, s)
                if os.path.exists(path):
                    d = load_markdown(path)
                    mds.append(d.markdown)
                    continue
            mds.append(s)

    return "\n".join(mds)

def stream(
    llm: Runnable,
    task: str=None,
    input: Union[str, List[str]]=None,
    sep_mode: str='all',
    knowledge: Union[str, List[str]]=None,
    prompt_id: str=None,
    base_folder: str=None,
    output_file: str=None,
    tag_start: str=None,
    tag_end: str=None,
    verbose: bool=False,
    is_fake: bool=False,
    template_folder: str=None,
    **kwargs
):
    """
    创作长文。
    
    - input: 除IDEA风格模板外，其他提示语模板大多需要输入依据文档，以便展开扩写、翻译、修改等任务
             这些依据文档可以为一个或多个，可以是字符串或文件；
             这些依据文档会被合并，作为连续的上下文。
    
    TODO: 支持更多任务拆分模式
    """
    base_folder = base_folder or ''
    prev_k = get_default_env("TEXTLONG_DOC_PREV_K")
    next_k = get_default_env("TEXTLONG_DOC_NEXT_K")
    prompt_id = prompt_id or 'IDEA'

    # front_matter
    args = {
        "task": task,
        "input": input,
        "sep_mode": sep_mode,
        "knowledge": knowledge,
        "prompt_id": prompt_id,
        "tag_start": tag_start,
        "tag_end": tag_end,
        "base_folder": base_folder,
        "template_folder": template_folder,        
    }
    not_empty_args = {k: args[k] for k in args if args[k]}
    dict_data = {
        'modified_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'output_file': output_file,
        'command': 'stream',
        'args': not_empty_args,
    }
    front_matter = create_front_matter({k: dict_data[k] for k in dict_data if dict_data[k]})
    yield ('front_matter', front_matter)
    
    # final output
    output_text = ""

    if (get_verbose() or verbose) and base_folder:
        yield ('info', f'\nbase_folder: {base_folder}\n')

    output_str = (prompt_id + " | " + output_file) if output_file else ""
    yield ('info', f'\n>->>> Prompt ID: {prompt_id}{output_str} <<<-<\n')

    # input
    input_doc = gather_docs(input, base_folder) or ''
    task_mode, task_todos, old_docs = 'all', [], []

    # knowledge
    kg_doc = gather_docs(knowledge, base_folder) or ''

    # prompt
    prompt = load_prompt(prompt_id, template_folder=template_folder)

    if input_doc:
        old_docs = MarkdownLoader(input_doc)
        task_mode, task_todos = old_docs.get_todo_documents(sep_mode)
        if get_verbose() or verbose:
            yield ('info', f'\nsep_mode: {sep_mode}\n')
            yield ('info', f'task_mode: {task_mode}\n')
            yield ('info', f'task_todos: {task_todos}\n\n')

    if task_mode == 'all':
        _kwargs = {
            "knowledge__": kg_doc,
            "todo_doc__": '\n'.join([d.page_content for d in task_todos]),
            **kwargs
        }
        chain = _create_chain(llm, prompt, **_kwargs)
        
        resp_md = ""
        for mode, delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
            if mode == 'chunk':
                resp_md += delta
            yield (mode, delta)
        output_text += resp_md
        yield ('final', resp_md)

    elif task_mode == 'document':
        last_index = None
        new_docs = copy.deepcopy(old_docs)
        for doc, index in task_todos:
            if last_index != None:
                md = "\n"
                output_text += md
                yield ('text', md)
            if old_docs.documents[last_index:index]:
                md = MarkdownLoader.to_markdown(old_docs.documents[last_index:index])
                output_text += md
                yield ('text', md)

            last_index = index + 1
            
            if doc.page_content and doc.page_content.strip():
                _kwargs = {
                    "knowledge__": kg_doc,
                    "todo_doc__": doc.page_content,
                    "prev_doc__": MarkdownLoader.to_markdown(new_docs.get_prev_documents(doc, prev_k)),
                    "next_doc__": MarkdownLoader.to_markdown(new_docs.get_next_documents(doc, next_k)),
                    **kwargs
                }
                chain = _create_chain(llm, prompt, **_kwargs)

                resp_md = ""
                for mode, delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
                    if mode == 'chunk':
                        resp_md += delta
                    yield (mode, delta)

                final_md = extract_text(resp_md, tag_start, tag_end)
                output_text += final_md
                yield ('final', final_md)

                reply_docs = parse_markdown(final_md)
                new_docs.replace_documents(doc, doc, reply_docs)

            else:
                # 如果内容是空行就不再处理
                output_text += doc.page_content
                yield ('text', doc.page_content)

        if old_docs.documents[last_index:None]:
            md = MarkdownLoader.to_markdown(old_docs.documents[last_index:None])
            output_text += md
            yield ('text', md)

    # 将输出文本保存到指定文件
    output_file = os.path.join(base_folder or "", output_file or "")
    if output_file and output_text:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(front_matter + output_text)
            yield ('warn', f'\n\n已保存 {output_file}, 共计 {len(output_text)} 字。\n')

def write(llm: Runnable, **kwargs):
    """
    打印流式日志。
    """

    output_text = ""

    for mode, chunk in stream(llm, **kwargs):
        if mode == 'text':
            output_text += chunk
            print(get_text_color() + chunk + "\033[0m", end="")
        elif mode == 'info':
            print(get_info_color() + chunk + "\033[0m", end="")
        elif mode == 'warn':
            print(get_warn_color() + chunk + "\033[0m", end="")
        elif mode == 'chunk':
            print(get_chunk_color() + chunk + "\033[0m", end="")
        elif mode == 'final':
            output_text += chunk
        elif mode == 'front_matter':
            output_text += chunk
    
    return output_text

def get_idea_args(prompt_id: str=None, **kwargs):
    kwargs.update({
        "sep_mode": "all",
        "prompt_id": prompt_id or "IDEA"
    })
    return kwargs

def get_outline_args(prompt_id: str=None, **kwargs):
    kwargs.update({
        "sep_mode": "all",
        "prompt_id": prompt_id or "OUTLINE"
    })
    return kwargs

def get_from_outline_args(prompt_id: str=None, **kwargs):
    kwargs.update({
        "sep_mode": "outline",
        "prompt_id": prompt_id or "FROM_OUTLINE",
        "tag_start": get_default_env("TEXTLONG_OUTLINE_START"),
        "tag_end": get_default_env("TEXTLONG_OUTLINE_END"),
    })
    return kwargs

def get_more_outline_args(prompt_id: str=None, **kwargs):
    kwargs.update({
        "sep_mode": "outline",
        "prompt_id": prompt_id or "MORE_OUTLINE",
        "tag_start": get_default_env("TEXTLONG_MORE_OUTLINE_START"),
        "tag_end": get_default_env("TEXTLONG_MORE_OUTLINE_END"),
    })
    return kwargs

def idea(llm: Runnable, prompt_id: str=None, **kwargs):
    if 'task' not in kwargs:
        raise ValueError("method <idea> need param <task> !!")
    return write(llm, **get_idea_args(prompt_id, **kwargs))

def outline(llm: Runnable, prompt_id: str=None, **kwargs):
    if 'task' not in kwargs:
        raise ValueError("method <outline> need param <task> !!")
    return write(llm, **get_outline_args(prompt_id, **kwargs))

def from_outline(llm: Runnable, prompt_id: str=None, **kwargs):
    if 'input' not in kwargs:
        raise ValueError("method <from_outline> need param <input> !!")
    return write(llm, **get_from_outline_args(prompt_id, **kwargs))

def more_outline(llm: Runnable, prompt_id: str=None, **kwargs):
    if 'input' not in kwargs:
        raise ValueError("method <more_outline> need param <input> !!")
    return write(llm, **get_more_outline_args(prompt_id, **kwargs))

