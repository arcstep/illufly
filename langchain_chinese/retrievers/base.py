from typing import List, Callable, Any, Optional, Type, Union
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, Runnable, RunnableAssign, chain
from langchain_core.output_parsers import StrOutputParser
from langchain.agents import tool
from langchain.tools import BaseTool
from langchain.pydantic_v1 import BaseModel, Field
from langchain.callbacks.manager import CallbackManagerForToolRun
from langchain_core.messages import BaseMessage
from functools import wraps
from operator import itemgetter

ASK_DOCUMENT_TOOL_NAME = "ask_document"

DEFAULT_QA_CHAIN_PROMPT = """
你要严格依据如下资料回答问题，你的回答不能与其冲突，更不要编造。
请始终使用中文回答。

{context}

问题: {question}
"""

def format_docs(docs: List[str]) -> str:
    return "\n\n".join([d.page_content for d in docs])

def convert_message_to_str(message: Union[BaseMessage, str]) -> str:
    if isinstance(message, BaseMessage):
        return message.content
    else:
        return message

def create_qa_chain(llm: Runnable, retriever: Callable, prompt: str = DEFAULT_QA_CHAIN_PROMPT) -> Callable:
    """
    使用 create_qa_chain 构建的LCEL链时，参数应当是一个消息。
    
    例如：    
    chain = creat_qa_chain(llm, rectriever)
    chain.invoke("langchain_chinese是啥？")
    """

    _prompt = ChatPromptTemplate.from_template(prompt)

    return (
        {
            "context": (lambda x: convert_message_to_str(x)) | retriever | format_docs,
            "question": lambda x: convert_message_to_str(x) ,
        }
        | _prompt
        | llm
    )

def make_safe_tool(func: Callable) -> Callable:
    """Create a new function that wraps the given function with error handling"""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return str(func(*args, **kwargs))
        except Exception as e:
            return str(e)
    return wrapper

class SearchInput(BaseModel):
    query: str = Field(
        title="提问内容",
        description="用户问题的文字描述，必须是字符串"
    )

class AskDocumentTool(BaseTool):
    name: str = ASK_DOCUMENT_TOOL_NAME
    description: str = """
    根据资料库回答问题。考虑上下文信息，确保问题对相关概念的定义表述完整。
    args:
    - query 类型是str, 用户问题的文字描述的字符串
    """
    args_schema: Type[BaseModel] = SearchInput
    qa_chain: Runnable = Field(...)

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        """Use the tool."""
        
        if isinstance(query, str):
            query = [query]
        return self.qa_chain.invoke([convert_message_to_str(q) for q in query])

def create_qa_toolkits(qa_chain: Runnable, name: str = None, description: str = None) -> List[AskDocumentTool]:
    return [AskDocumentTool(qa_chain, name, description)]
