import os
import copy
from typing import Union, List, Dict, Any
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose

from .markdown import MarkdownLoader
from .command import Command
from ..parser import parse_markdown
from ..hub import load_prompt
from ..importer import load_markdown
from ..utils import extract_text, color_code
from ..config import get_default_env

def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, input, is_fake: bool=False, verbose: bool=False):
    verbose_color = get_default_env("TEXTLONG_COLOR_VERBOSE")

    if get_verbose() or is_fake or verbose:
        print(color_code(verbose_color) + chain.get_prompts()[0].format(**input) + "\033[0m")

    if is_fake:
        yield "Fake-Output-Content...\n"
    else:
        for chunk in chain.stream(input):
            yield chunk.content

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

    if get_verbose() or verbose and base_folder:
        yield ('info', f'\nbase_folder: {base_folder}\n')

    prompt_id = prompt_id or 'IDEA'

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
        for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
            resp_md += delta
            yield ('log', delta)
        yield ('final', resp_md)

    elif task_mode == 'document':
        last_index = None
        new_docs = copy.deepcopy(old_docs)
        for doc, index in task_todos:
            if last_index != None:
                yield ('text', "\n")
            if old_docs.documents[last_index:index]:
                yield ('text', MarkdownLoader.to_markdown(old_docs.documents[last_index:index]))
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
                for delta in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
                    yield ('log', delta)
                    resp_md += delta
                final_md = extract_text(resp_md, tag_start, tag_end)
                yield ('final', final_md)
                reply_docs = parse_markdown(final_md)
                new_docs.replace_documents(doc, doc, reply_docs)

            else:
                # 如果内容是空行就不再处理
                yield ('info', '(无需处理的空行)\n')
                yield ('text', doc.page_content)

        if old_docs.documents[last_index:None]:
            yield ('text', MarkdownLoader.to_markdown(old_docs.documents[last_index:None]))

def write(
    llm: Runnable,
    output_file: str=None,
    base_folder: str=None,
    **kwargs
):
    """
    打印流式日志。
    
    - 返回值
        接收的流式内容都为形如 (mode, content) 的元组，其中：
        mode - 值为 text, final 或 log
        content - 文本内容

        log: 流式输出的中间结果，一般与collect或extract搭配使用
        text: 原始的文本结果直接被采纳
        final: 流式过程的最终结果收集，过程信息在log中分次输出
    """

    output_color = get_default_env("TEXTLONG_COLOR_OUTPUT")
    info_color = get_default_env("TEXTLONG_COLOR_INFO")
    log_color = get_default_env("TEXTLONG_COLOR_LOG")

    prompt_id = kwargs.get('prompt_id', 'IDEA')
    output_str = (" | " + output_file) if output_file else ""
    print(color_code(log_color) + f'\n>->>> Prompt ID: {prompt_id}{output_str} <<<-<\n' + "\033[0m")

    md = ''
    for mode, chunk in stream(
        llm,
        base_folder=base_folder,
        **kwargs
    ):
        if mode == 'text':
            md += chunk
            print(color_code(output_color) + chunk + "\033[0m", end="")
        elif mode == 'final':
            md += chunk
        elif mode == 'info':
            print(color_code(info_color) + chunk + "\033[0m", end="")
        elif mode == 'log':
            print(color_code(log_color) + chunk + "\033[0m", end="")
        else:
            print(color_code(log_color) + chunk + "\033[0m", end="")

    command = Command(
        command="write",
        args=kwargs,
        output_file=output_file,
        output_text=md
    )

    # 将输出文本保存到指定文件
    output_file = os.path.join(base_folder or "", output_file or "")
    if output_file:
        md_with_front_matter = MarkdownLoader.to_front_matter(command.to_metadata()) + md
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md_with_front_matter)
    
    return command

def idea(
    llm: Runnable,
    task: str=None,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "IDEA"
    return write(llm, task=task, sep_mode=sep_mode, prompt_id=prompt_id, **kwargs)

def outline(
    llm: Runnable,
    task: str=None,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "all"
    prompt_id = prompt_id or "OUTLINE"
    return write(
        llm,
        task=task,
        sep_mode=sep_mode,
        prompt_id=prompt_id,
        **kwargs
    )

def more_outline(
    llm: Runnable,
    input: Union[str, List[str]]=None,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "outline"
    prompt_id = prompt_id or "MORE_OUTLINE"
    return write(
        llm,
        sep_mode=sep_mode,
        input=input,
        prompt_id=prompt_id,
        tag_start=get_default_env("TEXTLONG_MORE_OUTLINE_START"),
        tag_end=get_default_env("TEXTLONG_MORE_OUTLINE_END"),
        **kwargs)

def from_outline(
    llm: Runnable,
    input: Union[str, List[str]]=None,
    prompt_id: str=None,
    **kwargs
):
    sep_mode = "outline"
    prompt_id = prompt_id or "FROM_OUTLINE"
    return write(
        llm,
        sep_mode=sep_mode,
        input=input,
        prompt_id=prompt_id,
        tag_start=get_default_env("TEXTLONG_OUTLINE_START"),
        tag_end=get_default_env("TEXTLONG_OUTLINE_END"),
        **kwargs
    )
