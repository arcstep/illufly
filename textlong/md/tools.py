from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain_core.runnables import Runnable
from langchain.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import StructuredTool
from .prompt import PROMPT_OUTLINE_WRITING, PROMPT_DETAIL_WRITING

def call_chain(chain, input):
    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")
    
    print(f"\n\n实际字数: {len(text)}")
    return text

def create_outline_chain(llm):
    prompt = PromptTemplate.from_template(PROMPT_OUTLINE_WRITING).partial(
        outline="暂无",
    )
    return prompt | llm

def create_detail_chain(llm):
    prompt = PromptTemplate.from_template(PROMPT_DETAIL_WRITING).partial(
        outline="暂无",
        detail="暂无",
    )
    return prompt | llm

def create_toolkist(llm):
    return [
        StructuredTool.from_function(
            func=lambda task: call_chain(create_outline_chain(llm), {"task": task}),
            name="create_outline",
            description="创作写作提纲(task: str, 任务描述)",
        ),
        StructuredTool.from_function(
            func=lambda task: call_chain(create_detail_chain(llm), {"task": task}),
            name="create_detail",
            description="根据提纲扩写(task: str, 任务描述)",
        ),
    ]

def create_chains(llm):
    return {
        "outline": create_outline_chain(llm),
        "detail": create_detail_chain(llm)
    }