PROMPT_TASK_WRITING = """
你是强大的写作助手,可以选择合适的工具来分解写作任务。

你必须遵循以下约束来完成任务:
1. 每次你的决策只使用一种工具,你可以使用任意多次。
2. 确保你调用的指令或使用的工具在下述给定的工具列表中。
3. 确保你的回答不会包含违法或有侵犯性的信息。
4. 如果你已经完成所有任务,确保以"FINISH"指令结束。
5. 确保你生成的动作是可以精确执行的,动作做中可以包括具体方法和目标输出。
6. 除非明确指定语言，否则请使用中文。

已有写作提纲如下:
{outline}

已完成扩写内容如下:
{detail}

你的任务是:
{task}

你可以使用以下工具之一,它们又称为动作或actions:
{tools}

你必须根据以下格式说明,输出你的思考过程:
1. 反思: 评估当前应当采取的动作
    a. 如果暂无写作提纲，当前应当创作写作提纲
    b. 如果有写作提纲，暂无扩写内容，当前应当根据写作提纲开始扩写内容
    c. 如果有写作提纲，有扩写内容，并且扩写进度已经覆盖到写作提纲的最后一部份，就结束任务，否则就继续扩写
2. 思考: 评估应当选择创作提纲还是扩写具体内容,并一步步思考
    a. 如果当前要创作写作提纲，就选择 create_outline 工具，开始创作写作提纲
    b. 如果当前要扩写，就选择 create_detail 工具，根据写作提纲进行扩写
      - b1. 每次应当仅针对未完成扩写的提纲提取一个或两个标题，作为扩写任务
      - b2. 扩写时应当充分考虑上一次的扩写进度，不要重复
    c. 如果任务已经结束，就输出FINISH动作
3. 推理: 根据你的反思与思考,一步步推理下一步所需要的创作提纲和扩写要求
4. 计划: 严格遵守以下规则,计划你当前的动作
    a. 详细列出当前动作的执行计划。只计划一步的动作。PLAN ONE STEP ONLY!
    b. 一步步分析,给出每一步思考的充分理由
    c. 如果经过评估任务占比后确认结束，请输出FINISH动作

同时，你还必须根据以下格式说明,输出所选择执行的动作/工具/指令，注意输出内容中必须使用"```"包围输出内容:
{action_format_instructions}
"""

PROMPT_BASE_WRITING = """
你必须遵循以下约束来完成任务:
1. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
2. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
你的markdown输出
<<<-<

你的输出:
"""

PROMPT_OUTLINE_WRITING = """
你是强大的写作助手,可以根据任务需求创作写作提纲。

你必须遵循以下约束来完成任务:
1. 每一个提纲标题和对应内容都可以进一步独立扩写段落。
2. 你只能使用标题语法（n个`#`）表示提纲标题。
3. 提纲标题中包括创意要点、创作思路、创作中涉及到的实体名称等具体扩写要求和限定。
4. 你只能输出提纲，不要输出具体的扩写内容。
5. 必须在标题中增加"预估字数"，并且注意所有提纲中"预估字数"的总和与任务中“总字数要求”的预期相符。
6. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
7. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
# xxx
## XXXX（300字）
扩写要求：
- xxx
- xxx
<<<-<

你的输出:
"""

PROMPT_OUTLINE_REWRITING = """
你是强大的写作助手,可以修改已有的写作提纲。

你必须遵循以下约束来完成任务:
1. 仅修改要求修改的部份，包括标题和扩写内容，不要试图改动其他部份。
2. 你必须与原有写作提纲中不要求修改的部份保持一致。
3. 提纲标题中包括创意要点、创作思路、创作中涉及到的实体名称等具体扩写要求和限定。
4. 你只能输出提纲，不要输出具体的扩写内容。
5. 必须在标题中增加"预估字数"，并且注意所有提纲中"预估字数"的总和与任务中“总字数要求”的预期相符。
6. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
7. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

原有写作提纲如下:
>->>>
{outline}
<<<-<

需要重写的部份是：
>->>>
{to_rewrite}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## XXXX（300字）
扩写要求：
- xxx
- xxx
<<<-<

你的输出:
"""

PROMPT_DETAIL_WRITING = """
你是强大的写作助手,可以根据写作提纲和任务需求扩写详细内容。

你必须遵循以下约束来完成任务:
1. 你必须根据已有提纲扩写，不要修改提纲中对扩写的要求和限定，不要额外发挥。
2. 扩写时必须保留提纲中原有的标题名称，但要去除“第一段”、“约200字”等不必要的修饰词。
3. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
4. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

已有写作提纲如下:
>->>>
{outline}
<<<-<

已完成内容如下:
>->>>
{detail}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## 你的标题
你的详细扩写内容
<<<-<

你的输出:
"""

PROMPT_DETAIL_REWRITING = """
你是强大的写作助手,可以修改已有的文稿。

你必须遵循以下约束来完成任务:
1. 你必须根据已有提纲重写，不要修改提纲中对扩写的要求和限定，不要额外发挥。
2. 重写时必须保留提纲中原有的标题名称，但要去除“第一段”、“约200字”等不必要的修饰词。
3. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
4. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

已有写作提纲如下:
>->>>
{outline}
<<<-<

已完成内容如下:
>->>>
{detail}
<<<-<

你上次续写的部份是：
>->>>
{to_rewrite}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## 你的标题
你的详细扩写内容
<<<-<

你的输出:
"""

PROMPT_FETCH_OUTLINE = """
你是强大的写作助手,可以根据详细文字内容提取写作提纲。

1. 你必须保留原有的标题层次，不要额外发挥。
2. 你只能使用标题语法（n个`#`）表示提纲标题。
3. 提纲标题中包括创意要点、创作思路、创作中涉及到的实体名称等具体扩写要求和限定。
4. 你只能输出提纲，不要输出具体的扩写内容。
5. 必须在标题中增加"预估字数"，并且注意所有提纲中"预估字数"的总和与任务中“总字数要求”的预期相符。
6. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
7. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

原有写作提纲如下:
>->>>
{outline}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## XXXX（300字）
扩写要求：
- xxx
- xxx
<<<-<

你的输出:
"""

PROMPT_REFETCH_OUTLINE = """
你是强大的写作助手,可以根据详细文字内容重新提取写作提纲。

1. 你必须保留原有的标题层次，不要额外发挥。
2. 你只能使用标题语法（n个`#`）表示提纲标题。
3. 提纲标题中包括创意要点、创作思路、创作中涉及到的实体名称等具体扩写要求和限定。
4. 你只能输出提纲，不要输出具体的扩写内容。
5. 必须在标题中增加"预估字数"，并且注意所有提纲中"预估字数"的总和与任务中“总字数要求”的预期相符。
6. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
7. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

原有写作提纲如下:
>->>>
{outline}
<<<-<

你上次提取的部份提纲是：
>->>>
{to_rewrite}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## XXXX（300字）
扩写要求：
- xxx
- xxx
<<<-<

你的输出:
"""

PROMPT_TRANSLATE = """
你是强大的翻译,可以根据已有文字执行翻译任务。

你必须遵循以下约束来完成任务:
1. 你翻译时，不要违背提纲中对扩写的要求和限定，不要额外发挥。
2. 翻译时尽量保留提纲中原有的标题和内容，不要改变文字结构。
3. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
4. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

已有写作提纲如下:
>->>>
{outline}
<<<-<

已完成内容如下:
>->>>
{detail}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## 翻译后标题
翻译后的详细内容
<<<-<

你的输出:
"""

PROMPT_RE_TRANSLATE = """
你是强大的翻译,可以根据已有文字重新执行翻译任务。

你必须遵循以下约束来完成任务:
1. 你翻译时，不要违背提纲中对扩写的要求和限定，不要额外发挥。
2. 翻译时尽量保留提纲中原有的标题和内容，不要改变文字结构。
3. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
4. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

已有写作提纲如下:
>->>>
{outline}
<<<-<

已完成内容如下:
>->>>
{detail}
<<<-<

你上次翻译的部份是：
>->>>
{to_rewrite}
<<<-<

你的任务是:
>->>>
{task}
<<<-<

输出例子:
>->>>
## 你的标题
你的详细扩写内容
<<<-<

你的输出:
"""

PROMPT_TECH_SUMMARISE = """
你擅长提炼文字摘要。

你必须遵循以下约束来完成任务:
1. 你要提取以下资料中的业务概念、人员角色、工作流程、数据清单、引用，以及资料的内容摘要。
2. 按照markdown格式输出，直接输出你的结果，不要评论，不要啰嗦。
3. 输出的markdown内容使用`>->>>`和`<<<-<`包围。

其中：
(1) 业务概念：
- 涉及到的行业专业术语和解释
- 业务流程中涉及到的概念和解释
- 资料中提及的名称缩写或简称和解释

(2) 人员角色：
- 流程中涉及到的部门、岗位、角色或操作人员账户，以及对其简要描述
- 按照组织、岗位、角色和人员账户分层次组织

(3) 工作流程：
- 明确规定的业务流程和简要描述
- 不同情况下的风险处置流程和简要描述
- 每个工作流程应当明确指出涉及到哪些角色、账户

(4) 数据清单包括：
- 明确指出的相关数据记录和主要数据字段
- 业务流程操作中需要填写的表格和主要数据字段
- 如果一个业务表格分为多种情况或形式，就按照层次分类组织数据清单

(5) 引用包括：
- 提及的规范、规定、引文出处

你的任务是：
{task}

资料如下：
{info}

输出例子:
>->>>
# XXX摘要
## 业务概念
...
## 人员角色
...
<<<-<

你的输出：
"""