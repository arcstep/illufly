from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

# help prompt
QA_SYSTEM_PROMPT = """
你是一名咨询专家，只负责根据资料回答相关提问，禁止回答与此无关的问题。

1. 如果你获得的参考例子无法回答问题，可以查询互联网，但务必注意资料的真实性，不要做任何编造
2. 请使用简洁的语言回答，不要啰嗦
3. 不要生成"根据提供的资料..."等字眼
"""

QA_OUTPUT_FORMAT = """
输出样例：
```
问题答案：xxx。

相关规范解释：xxxxxxxx
```
"""

def create_qa_prompt():
    """根据QA问答资料回答问题"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", "{{task_instruction}}"),
        ("ai", "我有哪些资料可以参考？"),
        ("human", "你可以参考这些资料：\n{{context}}\n你必须按照如下格式输出：{{output_format}}"),
        ("ai", "好的，我会优先从上面资料寻找答案，如果找不到合适的就会从互联网查询。"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{{question}}"),
    ], template_format="mustache").partial(
        task_instruction=QA_SYSTEM_PROMPT,
        output_format=QA_OUTPUT_FORMAT,
    )

    return prompt

def create_chat_prompt():
    """普通对话"""

    prompt = ChatPromptTemplate.from_messages([
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ])

    return prompt
