from typing import Any, AsyncIterator, Iterator, AsyncIterator, List, Union
from langchain_core.runnables import Runnable, RunnableGenerator
from langchain_core.runnables.utils import Input, Output
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessageChunk
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

class WritingInput(BaseModel):
    """
    使用 chain 时应当提交以下参数。
    
    其中，output_file 可以在使用时指定，而 base_folder 等其他参数只能在构建链时指定。
    """
    task: str=None
    input: Union[str, List[str]]=None
    knowledge: Union[str, List[str]]=None
    output_file: str=None
    prompt_id: str=None

def create_chain(llm: Runnable, **kwargs) -> Runnable[Input, Output]:
    """
    构建执行链。
    """
    def gen(input: Iterator[Any]) -> Iterator[str]:
        for input_args in input:
            for m, x in stream(llm, **{**kwargs, **input_args}):
                if m in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=x))

    async def agen(input: AsyncIterator[Any]) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        async for input_args in input:
            func_result = await loop.run_in_executor(
                executor,
                lambda: list(stream(llm, **{**kwargs, **input_args}))
            )
            for m, x in func_result:
                if m in ['text', 'chunk', 'front_matter']:
                    yield(AIMessageChunk(content=x))

    # 为了兼容 langserve，需要将 RunnableGenerator 转换为非迭代的返回
    chain = RunnableGenerator(gen, agen).with_types(input_type=WritingInput, output_type=Iterator[str]) | StrOutputParser()

    return chain

def create_idea_chain(llm: Runnable, **kwargs):
    return create_chain(llm, **get_idea_args(**kwargs))

def create_outline_chain(llm: Runnable, **kwargs):
    return create_chain(llm, **get_outline_args(**kwargs))

def create_from_outline_chain(llm: Runnable, **kwargs):
    return create_chain(llm, **get_from_outline_args(**kwargs))

def create_more_outline_chain(llm: Runnable, **kwargs):
    return create_chain(llm, **get_more_outline_args(**kwargs))

