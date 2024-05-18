from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

# help prompt
HELP_SYSTEM_PROMPT = """
你是一名优秀的写手，负责提供写作咨询。
"""

# main chat prompt
MAIN_PROMPT = """
{{task_instruction}}
请务必记住：{{json_instruction}}
请严格按如下格式输出JSON:{{output_format}}
始终使用中文，且不要输出JSON以外的内容，不要道歉，不要啰嗦。
"""

# task_instruction

_INIT_TASK = "你是一名优秀的写手，任务是对写作任务做评估，给出总体写作建议。"
_OUTLINE_TASK = "你是一名优秀的写手，可以构思写作思路、扩展写作提纲。"
_PARAGRAPH_TASK = "你是一名优秀的写手，负责详细构思段落细节。"

# json_instruction

_JSON_INSTRUCTION = "".join([
    "1. 你只能输出一个JSON段落，否则我将无法正确解析。",
    "2. 你必须严格遵循我提出的JSON键值规则，不要额外发挥，否则我将无法正确解析。",
    "3. 如果你的创作中出现实体名称、创作设定等，就将其单独提炼到扩写指南或内容摘要；",
    "这样做非常必要，可以让独立的创作子任务保持一致的背景设定。",
])

# output_format

_INIT_FORMAT = """
（请确保输出符合JSON语法限定，并且不要出现其他的JSON键，以便我能够正确解析）
```json
{
    "总字数要求": [int类型]预计的总体字数要求，默认为1000字,
    "标题名称": [str类型]根据写作任务，给出用户要求或你推荐的标题名称，不要带编号,
    "扩写指南": [str类型]应当尽量包含写作任务中提及的写作要求，也可以包含你的创作建议中所涉及的人物、地点、情节等实体名称和背景设定
}
```
"""

_OUTLINE_FORMAT = """
（请确保大纲列表中至少两个子项；确保输出符合JSON语法限定，并且不要出现其他的JSON键，以便我能够正确解析）
```json
{
    "大纲列表": [
        {
            "总字数要求": [int类型]段落的字数要求,
            "标题名称": [str类型]不带编号的标题名称,
            "扩写指南": [str类型]可以包含涉及的人物、地点、情节等实体名称和背景设定
        },
        ...,
        {
            "总字数要求": [int类型]段落的字数要求,
            "标题名称": [str类型]不带编号的标题名称,
            "扩写指南": [str类型]可以包含涉及的人物、地点、情节等实体名称和背景设定
        }
    ]
}
```
"""

_PARAGRAPH_FORMAT = """
（请确保输出符合JSON语法限定，并且不要出现其他的JSON键，以便我能够正确解析）
```json
{
    "详细内容": [str类型]你的详细输出,
    "内容摘要": [str类型]详细内容提要，可以包括涉及的人物、地点、情节等实体名称和背景设定
}
```
"""

# 自动生成编写大纲或段落
_AUTO_OUTLINE_OR_PARAGRAPH_PROMPT = """
你现在的任务是编写《{{title}}》，字数大约为{{words_advice}}字。
扩写依据为：{{howto}}
注意，你所写的内容是下面总提纲的一部份：
{{outline_exist}}
"""


def create_writing_help_prompt(system_prompt:str = None):
    """咨询系统如何使用"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt or HELP_SYSTEM_PROMPT),
        ("ai", "OK"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{{task}}"),
    ], template_format="jinja2")
    
    return prompt

def create_writing_init_prompt(main_prompt=None, task_prompt=None, output_format=None, json_instruction=None):

    prompt = ChatPromptTemplate.from_messages([
        ("system", main_prompt or MAIN_PROMPT),
        ("ai", "OK"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{{task}}"),
    ], template_format="jinja2").partial(
        # 任务指南
        task_instruction=task_prompt or _INIT_TASK,
        # 输出格式要求
        output_format=output_format or _INIT_FORMAT,
        # JSON严格控制
        json_instruction=json_instruction or _JSON_INSTRUCTION,
    )

    return prompt

def create_writing_todo_prompt(
    title: str,
    content_type: str="paragraph",
    words_limit: int=500,
    words_advice: int=500,
    howto: str=None,
    outline_exist: List[Any]=None,
    main_prompt: str=None,
    auto_prompt: str=None,
    json_instruction: str=None,
):
    main_prompt = MAIN_PROMPT
    auto_prompt = _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT
    json_instruction = _JSON_INSTRUCTION 

    if content_type == "outline":
        task_prompt   = _OUTLINE_TASK
        output_format = _OUTLINE_FORMAT
    else:
        task_prompt   = _PARAGRAPH_TASK
        output_format = _PARAGRAPH_FORMAT

    prompt = ChatPromptTemplate.from_messages([
        ("system", main_prompt),
        ("ai", "有什么具体要求？"),
        ("human", auto_prompt),
        ("ai", "OK"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{{task}}")
    ], template_format="jinja2").partial(
        # 字数限制
        words_limit=words_limit,
        words_advice=words_advice,
        # 写作要求
        title=title,
        outline_exist=outline_exist,
        task_instruction=task_prompt,
        howto=howto,
        # 输出格式要求
        output_format=output_format,
        # JSON严格控制
        json_instruction=json_instruction,
    )

    return prompt
