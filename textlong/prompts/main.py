from langchain_core.prompts import ChatPromptTemplate
from langchain.prompts import MessagesPlaceholder

SYSTEM_PROMPT = """
你是强大的AI写作助手。

## 写作目标
{goal}

## 指导原则
{instruction}

## 你的思考过程必须考虑下面提供的资料内容
{knowledge}

## 你的输出不得与如下观点相违背
{rules}

## 你的写作风格必须符合以下要求
{styles}

## 你的输出格式必须为：{format}

## 你的输出内容必须参考如下示例
{demo}

"""

# openai agent
OPENAI_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("agent_scratchpad", optional=True),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
])

# chain
CHAIN_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
])
