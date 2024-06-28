from typing import Any, AsyncIterator, Iterator, AsyncIterator, List, Union, Dict
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.runnables.utils import Input, Output
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessageChunk
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tracers.schemas import Run

from ..project.base import Project
from ..config import get_folder_docs, get_default_output, get_default_env
from ..writing import stream
from ..writing.base import (
    get_idea_args,
    get_outline_args,
    get_from_outline_args,
    get_more_outline_args,
)

import asyncio
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=get_default_env("TEXTLONG_MAX_WORKERS"))

class WritingInput(BaseModel):
    """
    使用 chain 时应当提交以下参数。
    
    其中，output_file 可以在使用时指定，而 base_folder 等其他参数只能在构建链时指定。
    """
    task: str=None
    input: Union[str, List[str]]=None
    knowledge: Union[str, List[str]]=None
    project_id: str=None
    output_file: str=None
    prompt_id: str=None

def create_chain(llm: Runnable, base_folder: str=None, **kwargs) -> Runnable[Input, Output]:
    """
    构建执行链。
    """

    def gen(input: Iterator[Any]) -> Iterator[str]:
        for input_args in input:
            project_id = input_args.get('project_id', get_folder_docs())
            project = Project(project_id, base_folder, llm)
            kwargs['base_folder'] = project.project_folder
            args = {**kwargs, **get_default_args(input_args)}

            output_text = ''
            for m, x in stream(llm, **args):
                if m in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=x))
                    output_text += x

            output_file = kwargs['output_file']
            project.save_output_history(output_file, output_text)
            if output_file not in project.output_files:
                project.output_files.add(output_file)
                project.save_project()

    async def agen(input: AsyncIterator[Any]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        async for input_args in input:
            project_id = input_args.get('project_id', get_folder_docs())
            project = Project(project_id, base_folder, llm)

            kwargs['base_folder'] = project.project_folder
            args = {**kwargs, **get_default_args(input_args)}

            res = await loop.run_in_executor(executor, lambda: list(stream(llm, **args)))
            output_text = ''
            for m, x in res:
                if m in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=x))
                    output_text += x

            output_file = args['output_file']
            project.save_output_history(output_file, output_text)
            if output_file not in project.output_files:
                project.output_files.add(output_file)
                project.save_project()

    # 为了兼容 langserve，需要将 RunnableGenerator 转换为非迭代的返回
    return RunnableGenerator(gen, agen).with_types(
        input_type=WritingInput,
        output_type=Iterator[str]
    ) | StrOutputParser()

def get_default_args(input_args: Dict[str, Any]):
    action = input_args.get("action", "idea")
    if action == "idea":
        default_args = get_idea_args(**input_args)
    elif action == "outline":
        default_args = get_outline_args(**input_args)
    elif action == "from_outline":
        default_args = get_from_outline_args(**input_args)
    elif action == "more_outline":
        default_args = get_more_outline_args(**input_args)
    else:
        default_args = input_args

    default_args['output_file'] = input_args.get('output_file', get_default_output())
    return default_args
