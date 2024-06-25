from typing import Any, AsyncIterator, Iterator, AsyncIterator, List, Union
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.pydantic_v1 import BaseModel, Field
from ..writing import write, idea, outline, from_outline, more_outline

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

def _create_chain(llm: Runnable, writing_func):
    def gen(input: Iterator[Any]) -> Iterator[str]:
        for kwargs in input:
            for m, x in writing_func(llm, use_yield=True, **kwargs):
                if m != 'final':
                    yield(x)

    async def agen(input: AsyncIterator[Any]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        async for kwargs in input:
            func_result = await loop.run_in_executor(
                executor,
                lambda: list(writing_func(llm, use_yield=True, **kwargs))
            )
            for m, x in func_result:
                if m != 'final':
                    yield x

    return RunnableGenerator(gen, agen).with_types(input_type=writing_input, output_type=Iterator[str])

def create_idea_chain(llm: Runnable):
    return _create_chain(llm, idea)

def create_outline_chain(llm: Runnable):
    return _create_chain(llm, outline)

def create_from_outline_chain(llm: Runnable):
    return _create_chain(llm, from_outline)

def create_more_outline_chain(llm: Runnable):
    return _create_chain(llm, more_outline)

