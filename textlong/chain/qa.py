from typing import List, Callable, Any, Optional, Type, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.embeddings import Embeddings
from ..hub import load_prompt
from ..memory import MemoryManager, WithMemoryBinding
from ..knowledge.base import collect_docs

def create_qa_chain(
    llm: Runnable,
    retriever: Callable,
    memory: MemoryManager=None,
    prompt: str = None
) -> Callable:
    """
    构建QA链。
    """

    _prompt = load_prompt((prompt or "RAG"), tag="chat").partial(history="")

    if memory:
        chain = {
            "context":  (lambda x: x['input']) | retriever | collect_docs,
            "question": lambda x: x['input'],
            "history":  lambda x: x['history'],
        } | _prompt | llm
        return WithMemoryBinding(chain, memory)
    else:
        return {
            "context":  (lambda x: x) | retriever | collect_docs,
            "question": lambda x: x,
        } | _prompt | llm

def create_dynamic_qa_chain(chain_func: Callable):
    """
    动态构建QA链。
    """
    chain = chain_func()
    return chain
    