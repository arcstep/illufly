import os
import re
import copy
from datetime import datetime
from typing import Union, List, Dict, Any, Optional
from langchain_core.runnables import Runnable
from langchain_core.documents import Document
from langchain.globals import set_verbose, get_verbose
from langchain_core.messages import BaseMessage
from langchain.memory import ConversationBufferWindowMemory
from langchain.memory.chat_memory import BaseChatMemory

from .message import TextChunk
from .markdown import MarkdownLoader
from .command import Command
from ..parser import parse_markdown, create_front_matter
from ..hub import load_prompt
from ..importer import load_markdown
from ..utils import extract_text, safety_path
from ..config import get_env

def _create_chain(llm, prompt_template, **kwargs):
    if not llm:
        raise ValueError("LLM can't be None !")
    prompt = prompt_template.partial(**kwargs)
    return prompt | llm

def _call_markdown_chain(chain, completed, is_fake: bool=False, verbose: bool=False):
    if get_verbose() or is_fake or verbose:
        yield TextChunk('info', chain.get_prompts()[0].format(**completed))

    if is_fake:
        yield TextChunk('info', "Fake-Output-Content...\n")
    else:
        for chunk in chain.stream(completed):
            if isinstance(chunk, BaseMessage):
                yield TextChunk('chunk', chunk.content)
            else:
                yield TextChunk('chunk', chunk)

def gather_docs(completed: Union[str, List[str]], base_folder: str="") -> str:
    """
    从input收集文本，有如下情况：
    - 文本字符串
    - 文本字符串列表
    - 一个包含文本的文件，一般为md格式
    - 一组包含文本的文件，一般为md格式
    
    TODO: 支持 word、html 等其他格式
    """

    mds = []

    if isinstance(completed, str):
        completed = [completed]

    if isinstance(completed, list):
        for s in completed:
            s = safety_path(s)
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
    completed: Union[str, List[str]]=None,
    sep_mode: str='all',
    knowledge: Union[str, List[str]]=None,
    prompt_id: str=None,
    prompt_tag: str=None,
    base_folder: str=None,
    output_file: str=None,
    tag_start: str=None,
    tag_end: str=None,
    verbose: bool=False,
    is_fake: bool=False,
    template_folder: str=None,
    memory: Optional[BaseChatMemory] = None,
    **kwargs
):
    """
    创作长文。
    
    - completed: 
        除IDEA风格模板外，其他提示语模板大多需要输入依据文档，以便展开扩写、翻译、修改等任务
        这些依据文档可以为一个或多个，可以是字符串或文件；
        这些依据文档会被合并，作为连续的上下文。
    
    TODO: 支持更多任务拆分模式
    """
    base_folder = base_folder or ''
    prev_k = get_env("TEXTLONG_DOC_PREV_K")
    next_k = get_env("TEXTLONG_DOC_NEXT_K")
    prompt_id = prompt_id or 'CHAT'
    output_file = safety_path(output_file) if output_file else None
    history = memory.buffer_as_str if memory else ''

    # front_matter
    args = {
        "task": task,
        "completed": completed,
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
    yield TextChunk('front_matter', front_matter)
    
    # final output
    output_text = ""

    if (get_verbose() or verbose) and base_folder:
        yield TextChunk('info', f'\nbase_folder: {base_folder}\n')

    output_str = (" | " + output_file) if output_file else ""
    yield TextChunk('info', f'\n>->>> Prompt ID: {prompt_id}{output_str} <<<-<\n')

    # completed
    input_doc = gather_docs(completed, base_folder) or ''
    task_mode, task_todos, old_docs = 'all', [], []

    # knowledge
    kg_doc = gather_docs(knowledge, base_folder) or ''

    # prompt
    prompt = load_prompt(prompt_id, template_folder=template_folder, tag=prompt_tag)

    if input_doc:
        old_docs = MarkdownLoader(input_doc)
        task_mode, task_todos = old_docs.get_todo_documents(sep_mode)
        if get_verbose() or verbose:
            yield TextChunk('info', f'\nsep_mode: {sep_mode}\n')
            yield TextChunk('info', f'task_mode: {task_mode}\n')
            yield TextChunk('info', f'task_todos: {task_todos}\n\n')

    if task_mode == 'all':
        _kwargs = {
            "knowledge__": kg_doc,
            "todo_doc__": '\n'.join([d.page_content for d in task_todos]),
            "history": history,
            **kwargs
        }
        chain = _create_chain(llm, prompt, **_kwargs)
        
        resp_md = ""
        for chunk in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
            if chunk.mode == 'chunk':
                resp_md += chunk.content
            yield chunk
        final_md = extract_text(resp_md, tag_start, tag_end)
        output_text += final_md
        yield TextChunk('final', final_md)

    elif task_mode == 'document':
        last_index = None
        new_docs = copy.deepcopy(old_docs)
        for doc, index in task_todos:
            if last_index != None:
                md = "\n"
                output_text += md
                yield TextChunk('text', md)
            if old_docs.documents[last_index:index]:
                md = MarkdownLoader.to_markdown(old_docs.documents[last_index:index])
                output_text += md
                yield TextChunk('text', md)

            last_index = index + 1
            
            if doc.page_content and doc.page_content.strip():
                _kwargs = {
                    "knowledge__": kg_doc,
                    "todo_doc__": doc.page_content,
                    "prev_doc__": MarkdownLoader.to_markdown(new_docs.get_prev_documents(doc, prev_k)),
                    "next_doc__": MarkdownLoader.to_markdown(new_docs.get_next_documents(doc, next_k)),
                    "history": "",
                    **kwargs
                }
                chain = _create_chain(llm, prompt, **_kwargs)

                resp_md = ""
                for chunk in _call_markdown_chain(chain, {"task": task}, is_fake, verbose):
                    if chunk.mode == 'chunk':
                        resp_md += chunk.content
                    yield chunk

                final_md = extract_text(resp_md, tag_start, tag_end)
                to_insert = new_docs.replace_documents(doc, doc, final_md)
                final_md_strip = MarkdownLoader.to_markdown(to_insert).strip()

                output_text += final_md_strip
                yield TextChunk('final', final_md_strip)

            else:
                # 如果内容是空行就不再处理
                output_text += doc.page_content
                yield TextChunk('text', doc.page_content)

        if old_docs.documents[last_index:None]:
            md = MarkdownLoader.to_markdown(old_docs.documents[last_index:None])
            output_text += md
            yield TextChunk('text', md)
    
    # 记忆
    if memory:
        memory.save_context({"input": task}, {"output": output_text})

    # 将输出文本保存到指定文件
    output_file = os.path.join(base_folder or "", output_file or "")
    if output_file and output_text:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(front_matter + output_text)
            yield TextChunk('warn', f'\n\n已保存 {output_file}, 共计 {len(output_text)} 字。\n')

def stream_log(llm: Runnable, **kwargs):
    """
    打印流式日志。
    """

    output_text = ""

    for chunk in stream(llm, **kwargs):
        if chunk.mode in ['text', 'final', 'front_matter']:
            output_text += chunk.text

        if chunk.mode in ['info', 'warn', 'text', 'chunk']:
            print(chunk.text_with_print_color, end="")
    
    return output_text

def get_default_writing_args(command: str=None, **kwargs):
    if not command:
        command = "chat"
    default_args = {
        "idea": {
            "sep_mode": "all",
            "prompt_id": "IDEA",
            "tag_start": get_env("TEXTLONG_MARKDOWN_START"),
            "tag_end": get_env("TEXTLONG_MARKDOWN_END"),
        },
        "chat": {
            "sep_mode": "all",
            "prompt_id": "CHAT",
            "tag_start": get_env("TEXTLONG_MARKDOWN_START"),
            "tag_end": get_env("TEXTLONG_MARKDOWN_END"),
        },
        "outline": {
            "sep_mode": "all",
            "prompt_id": "OUTLINE",
            "tag_start": get_env("TEXTLONG_MARKDOWN_START"),
            "tag_end": get_env("TEXTLONG_MARKDOWN_END"),
        },
        "from_outline": {
            "task": "请帮我扩写。",
            "sep_mode": "outline",
            "prompt_id": "FROM_OUTLINE",
            "tag_start": get_env("TEXTLONG_OUTLINE_START"),
            "tag_end": get_env("TEXTLONG_OUTLINE_END"),
        },
        "more_outline": {
            "task": "请帮我生成更多提纲。",
            "sep_mode": "outline",
            "prompt_id": "MORE_OUTLINE",
            "tag_start": get_env("TEXTLONG_MORE_OUTLINE_START"),
            "tag_end": get_env("TEXTLONG_MORE_OUTLINE_END"),
        }
    }
    if command in default_args:
        new_args = default_args[command]
        new_args.update(kwargs)
        return new_args
    else:
        return kwargs

def idea(llm: Runnable, **kwargs):
    if 'task' not in kwargs:
        raise ValueError("method <chat> need param <task> !!")
    return stream_log(llm, **get_default_writing_args('idea', **kwargs))

def chat(llm: Runnable, **kwargs):
    if 'task' not in kwargs:
        raise ValueError("method <chat> need param <task> !!")
    return stream_log(llm, **get_default_writing_args('chat', **kwargs))

def outline(llm: Runnable, **kwargs):
    if 'task' not in kwargs:
        raise ValueError("method <outline> need param <task> !!")
    return stream_log(llm, **get_default_writing_args('outline', **kwargs))

def from_outline(llm: Runnable, **kwargs):
    if 'completed' not in kwargs:
        raise ValueError("method <from_outline> need param <completed> !!")
    return stream_log(llm, **get_default_writing_args('from_outline', **kwargs))

def more_outline(llm: Runnable, **kwargs):
    if 'completed' not in kwargs:
        raise ValueError("method <more_outline> need param <completed> !!")
    return stream_log(llm, **get_default_writing_args('more_outline', **kwargs))

