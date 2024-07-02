from typing import Any, AsyncIterator, Iterator, AsyncIterator, List, Union, Dict
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.runnables.utils import Input, Output
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessageChunk
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tracers.schemas import Run

from ..project.base import BaseProject
from ..config import  get_env
from ..writing import stream, get_default_writing_args

import asyncio
from concurrent.futures import ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=get_env("TEXTLONG_MAX_WORKERS"))

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

    default_output = get_env("TEXTLONG_DEFAULT_OUTPUT")

    def gen(input: Iterator[Any]) -> Iterator[str]:
        for input_args in input:
            project_id = input_args.get('project_id', get_env("TEXTLONG_DOCS") or "DEFAULT")
            project = BaseProject(project_id, base_folder)
            input_args['base_folder'] = project.project_folder
            output_file = input_args.get("output_file", default_output) or default_output
            input_args['output_file'] = output_file
            command = input_args.get("action", "chat")
            args = {**input_args, **get_default_writing_args(command, **input_args)}

            output_text = ''
            for chunk in stream(llm, **args):
                if chunk.mode in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=chunk.content))
                    output_text += chunk.content

            project.save_output_history(output_file, output_text)
            if output_file not in project.output_files:
                project.output_files.add(output_file)
                project.save_project()

    async def agen(input: AsyncIterator[Any]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        async for input_args in input:
            project_id = input_args.get('project_id', get_env("TEXTLONG_DOCS") or "DEFAULT")
            project = BaseProject(project_id, base_folder)

            input_args['base_folder'] = project.project_folder
            output_file = input_args.get("output_file", default_output) or default_output
            input_args['output_file'] = output_file
            command = input_args.get("action", "chat")
            args = {**input_args, **get_default_writing_args(command, input_args)}

            res = await loop.run_in_executor(executor, lambda: list(stream(llm, **args)))
            output_text = ''
            for chunk in res:
                if chunk.mode in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=chunk.content))
                    output_text += chunk.content

            project.save_output_history(output_file, output_text)
            if output_file not in project.output_files:
                project.output_files.add(output_file)
                project.save_project()

    return RunnableGenerator(gen, agen).with_types(
        input_type=WritingInput,
        output_type=Iterator[str]
    ) | StrOutputParser()
