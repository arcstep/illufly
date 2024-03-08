from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

__DEFAULT_QA_CHAIN_PROMPT = """Answer the question based only on the following context:

{context}

Question: {question}
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

def create_qa_tools():
    pass

def create_qa_tools_agent():
    pass

def create_qa_react_agent():
    pass
