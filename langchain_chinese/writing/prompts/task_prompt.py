MAIN_PROMPT = """
{{task_instruction}}

请务必记住：
{{json_instruction}}

请严格按如下格式输出JSON:
{{output_format}}

不要输出JSON以外的内容。
"""

# task_instruction

_ROOT_TASK = "你是一名优秀的写手，任务是对写作任务做评估，给出总体写作建议。"
_OUTLINE_TASK = "你是一名优秀的写手，可以构思写作思路、扩展写作提纲。"
_PARAGRAPH_TASK = "你是一名优秀的写手，负责详细构思段落细节。"

# json_instruction

_JSON_INSTRUCTION = """
1. 你只能输出一个JSON段落，否则我将无法正确解析。
2. 你必须严格遵循我提出的JSON键值规则，不要额外发挥，否则我将无法正确解析。
3. 在拆分提纲时，每个子任务的字数要求不要低于200字。
4. 如果你的创作中出现实体名称、创作设定等，就将其单独提炼到扩写指南或内容摘要；
   这样做非常必要，可以让独立的创作子任务保持一致的背景设定。
"""

# output_format

_ROOT_FORMAT = """
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
（请确保输出符合JSON语法限定，并且不要出现其他的JSON键，以便我能够正确解析）
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
你现在的写作任务是针对提纲《{{title}}》，字数大约为{{words_advice}}字。
扩写依据为：{{howto}}。
注意，你所写的提纲是下面总体提纲的一部份：
{{outline_exist}}
"""

__all__ = [
    "MAIN_PROMPT",
    "_ROOT_TASK",
    "_OUTLINE_TASK",
    "_PARAGRAPH_TASK",
    "_JSON_INSTRUCTION",
    "_ROOT_FORMAT",
    "_OUTLINE_FORMAT",
    "_PARAGRAPH_FORMAT",
    "_AUTO_OUTLINE_OR_PARAGRAPH_PROMPT",
]