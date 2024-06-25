from typing import Any, AsyncIterator, Iterator, AsyncIterator, List, Union
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.tracers.schemas import Run

from ..writing.base import (
    stream,
    get_idea_args,
    get_outline_args,
    get_from_outline_args,
    get_more_outline_args,
)

import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

class writing_input(BaseModel):
    task: str=None
    input: Union[str, List[str]]=None
    knowledge: Union[str, List[str]]=None
    output_file: str=None
    base_folder: str=None
    prompt_id: str=None

def create_chain(llm: Runnable, **kwargs):
    """
    构建执行链。
    """
    def gen(input: Iterator[Any]) -> Iterator[str]:
        for input_args in input:
            for m, x in stream(llm, use_yield=True, **kwargs, **input_args):
                if m in ['text', 'chunk', 'front_matter']:
                    yield(x)

    async def agen(input: AsyncIterator[Any]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        async for input_args in input:
            func_result = await loop.run_in_executor(
                executor,
                lambda: list(stream(llm, **kwargs, **input_args))
            )
            for m, x in func_result:
                if m in ['text', 'chunk', 'front_matter']:
                    yield x

    return RunnableGenerator(gen, agen).with_types(input_type=writing_input, output_type=Iterator[str])

def create_idea_chain(llm: Runnable, prompt_id: str=None, **kwargs):
    return create_chain(llm, **get_idea_args(prompt_id, **kwargs))

def create_outline_chain(llm: Runnable, prompt_id: str=None, **kwargs):
    return create_chain(llm, **get_outline_args(prompt_id, **kwargs))

def create_from_outline_chain(llm: Runnable, prompt_id: str=None, **kwargs):
    return create_chain(llm, **get_from_outline_args(prompt_id, **kwargs))

def create_more_outline_chain(llm: Runnable,prompt_id: str=None,  **kwargs):
    return create_chain(llm, **get_more_outline_args(prompt_id, **kwargs))

