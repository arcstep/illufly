from .tool_factory import create_tool, create_chain

详细任务指引 = """
你是一位专业作者，负责创作写作的详细内容，确保符合下面要求。

MUST 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
MUST 输出的markdown内容使用`>->>>`和`<<<-<`包围。
"""

提纲任务指引 = """
你是一位专业作者，负责创作写作的详细内容，确保符合下面要求。

MUST 每一个标题都应当是可以进一步独立扩写的段落。
MUST 你只能使用标题语法（n个`#`）表示提纲。
MUST 提纲中包括扩写要求，包括创意要点、创作思路、创作中涉及到的实体名称等。
MUST 你只能输出提纲，不要输出具体内容。
MUST 必须在标题中增加字数估计，并且注意所有段落字数总和符合对总字数的预期。
MUST 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
MUST 输出的markdown内容使用`>->>>`和`<<<-<`包围。
"""

提纲格式输出 = """
输出例子:
>->>>
# xxx
## XXXX（300字）
扩写要求：
- xxx
- xxx
## XXXX（200字）
扩写要求：
- xxx
- xxx
<<<-<
"""

内容格式输出 = """
输出例子（一定不要在标题中带有“第一章”、“第一节”、“1.1“等编号）:
>->>>
# xxx
## XXXX
xxxx
## XXXX
xxxx
<<<-<
"""

详细扩写补充要求 = """
MUST 扩写时必须保留提纲中原有的标题名称，但要去除“第一段”、“约200字”等不必要的修饰词，也可以根据实际情况修改编号。

你的扩写依据如下：
{outline}
"""

提纲扩写补充要求 = """
MUST 你要么保留已有提纲结构，要么对已有提纲标题进一步增加层次，创作更深层次的提纲结构。
MUST 对于保留的提纲结构，应当保留提纲名称和字数约束。

你的扩写依据如下：
{outline}
"""

all_tools = [
    {
        "name": "detail",
        "args": [
            ("task", "[str] 写作目标"),
        ],
        "prompt": 详细任务指引 + 内容格式输出,
        "description": "当你有写作任务时，优先使用此工具直接按要求创作详细的文字内容"
    },
    {
        "name": "outline",
        "args": [
            ("task", "[str] 写作目标"),
        ],
        "prompt": 提纲任务指引 + 提纲格式输出,
        "description": "当你的创作任务结构较复杂、字数较多，不要直接创作文字，而是给出一个符合要求的写作大纲"
    },
    {
        "name": "expand_detail",
        "args": [
            ("task", "[str] 写作目标"),
        ],
        "prompt": 详细任务指引 + 提纲扩写补充要求 + 内容格式输出,
        "description": "根据写作大纲细化详细内容文字内容"
    },
    {
        "name": "expand_outline",
        "args": [
            ("task", "[str] 写作目标"),
        ],
        "prompt": 提纲任务指引 + 提纲扩写补充要求 + 提纲格式输出,
        "description": "根据写作大纲细化写作大纲"
    },
]

toolkits = [
    create_tool(
        name=item['name'],
        prompt=item['prompt'],
        description=item['description'] \
            + "(kwargs: " \
            + ";".join([f'{arg} {desc}' for arg, desc in item['args']]) \
            + ")",
    ) for item in all_tools
]

chains = {}

for item in all_tools:
    chains.update(create_chain(item['prompt'], item['name']))
