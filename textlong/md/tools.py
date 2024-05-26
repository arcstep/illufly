from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import StructuredTool

def _get_chain(prompt):
    _prompt = ChatPromptTemplate.from_messages([
        ("system", f"{prompt}"),
        ("human", "{task}")
    ])
    
    from langchain_zhipu import ChatZhipuAI
    llm = ChatZhipuAI()
    chain = _prompt | llm

    return chain

def call_chain(chain, input):
    text = ""
    for chunk in chain.stream(input):
        text += chunk.content
        print(chunk.content, end="")
    
    print(f"\n\n实际字数: {len(text)}")
    return text

def create_tool(prompt:str, name: str, description: str):
    """
    创建写作工具。
    """

    return StructuredTool.from_function(
        func=lambda **kwargs: call_chain(_get_chain(prompt), kwargs),
        name=name,
        description=description,
    )

def create_chain(prompt:str, name: str):
    """
    创建写作链。
    """

    return ({name: _get_chain(prompt)})
