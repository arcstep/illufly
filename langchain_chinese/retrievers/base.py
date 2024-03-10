from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain.agents import Tool
from langchain.tools import StructuredTool
from functools import wraps

__DEFAULT_QA_CHAIN_PROMPT = """
你要严格依据如下资料回答问题，你的回答不能与其冲突，更不要编造。
请始终使用中文回答。

{context}

问题: {question}
"""

def create_qa_chain(llm, retriever, prompt = __DEFAULT_QA_CHAIN_PROMPT):
    prompt = ChatPromptTemplate.from_template(prompt)

    def format_docs(docs):
        return "\n\n".join([d.page_content for d in docs])

    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
    )

# 将函数安全地转换为工具，并在抛出异常时仍然正常返回
def make_safe_tool(func):
    """Create a new function that wraps the given function with error handling"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return str(func(*args, **kwargs))
        except Exception as e:
            return str(e)
    return wrapper

# 基于本地知识库
def create_qa_tool(
    qa_chain,
    tool_name="ask_document",
    description="""
    根据资料库回答问题。考虑上下文信息，确保问题对相关概念的定义表述完整。
    Args:
    - question:str 必填，用户问题的文字描述
    """
):
    document_qa_tool = StructuredTool.from_function(
        func=make_safe_tool(lambda query: qa_chain.invoke(query)),
        name=tool_name,
        description=description,
    )
    return document_qa_tool

def create_qa_toolkits(qa_chain):
    return [create_qa_tool(qa_chain)]
