from typing import Any, Dict, Iterator, List, Optional, Union
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain_zhipu import ChatZhipuAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from .content import TreeContent
import json
import re

OUTLINE_INSTRUCTIONS = """
你是一名优秀的写手，可以构思写作思路、扩展写作提纲、细化段落内容，

请务必记住：
1. 当你收到新的写作任务，你应当做两种选择，要么输出写作提纲，要么输出细化的写作内容。
2. 你输出的内容规定为最大不超过300字，因此你必须严格按照如下规则决定该如何输出：
（1）如果发现用户要求的字数超出了最大限制，你就必须输出写作提纲；
（2）反之，如果你发现用户要求的字数不超过限制，你就必须输出段落内容。
（3）如果你决定输出写作提纲，那么大纲数量必须大于2，否则还是直接输出为段落内容。

例如：
用户要求字数1500字左右，此时超出了300字的写作限定，你必须输出“写作提纲”，可以分为5个部份，每部份约300字左右；
用户要求字数80字左右，此时符合300字左右的限定，你必须输出为“段落内容”。

如果你决定输出“写作提纲”，就请按照如下格式输出写作大纲：
```json
{
    "类型": "outlines",
    "总字数要求": 预计的总体字数要求（int类型）,
    "大纲数量": 与以上列表相符的大纲数量,
    "大纲列表": [
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要},
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要},
        （...重复N行）
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要}
    ]
}
```

如果你决定输出“段落内容”，就请按照如下格式输出：
```json
{
    "类型": "paragraph",
    "总字数要求": 段落的字数要求（int类型）,
    "内容": "你的详细输出"
}
```

只输出上述的JSON内容即可，其他不必输出。
"""

PARAGRAPH_INSTRUCTIONS = """
你是一名优秀的写手，负责详细构思段落细节。

你必须按照如下格式输出：
```json
{
    "类型": "paragraph",
    "总字数要求": 段落的字数要求（int类型）,
    "内容": "你的详细输出"
}
```

只输出上述的JSON内容即可，其他不必输出。
"""

def get_input(prompt: str = "\n👤: ") -> str:
    return input(prompt)

class WritingTask(BaseModel):
    """
    写作管理。
    """
    root_content: Optional[TreeContent] = None
    cur_content: Optional[TreeContent] = None

    # 控制参数
    words_per_step = 300
    words_all_limit = 1000
    retry_max = 5

    # - 子任务可以配置为几种处置方案：skip / redo / askme / auto
    # - skip 可以跳过处理，采纳原有的结果或暂时不处理
    # - redo 重新分配 session_id 生成，但用户全部自动回复 OK 
    # - redon 未来可支持 Redo N 次，由 LLM 代替用户做最多 N 次评估
    # - askme 重新分配 session_id 生成，但要求用户介入评估
    # - auto
    task_mode = "askme"

    streaming = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_content = TreeContent()
        self.cur_content = self.root_content

        # 初始化参数
        keys = ["task_mode"]
        for k in keys:
            if k in kwargs:
                setattr(self, k, kwargs[k])
        print("task_mode:", self.task_mode)

    def next_step(self):
        pass

    def ask_user(self) -> tuple:
        resp = get_input()
        content = None
    
        if(resp == "quit"):
            command = "quit"
        elif(resp == "ok"):
            command = "ok"
        else:
            content = resp
            command = "chat"
    
        return content, command

    def get_chain(self):
        words = self.cur_content.words_advice
        if words == None or words > self.words_per_step:
            instruction = OUTLINE_INSTRUCTIONS
        else:
            instruction = PARAGRAPH_INSTRUCTIONS
        
        prompt_init = ChatPromptTemplate.from_messages([
            ("system", instruction),
            ("user", "{{input}}")
        ], template_format='jinja2')

        prompt_detail = ChatPromptTemplate.from_messages([
            ("system", instruction),
            ("assistant", "之前的写作提纲为: {{outlines}}"),
            ("user", "{{input}}。请注意，你现在的写作任务是上面已有提纲的一部份")
        ], template_format='jinja2')

        return (prompt_init | ChatZhipuAI() | JsonOutputParser())

    def run(self):
        # 初始化链
        chain = self.get_chain()
        ai_said = {}
        user_said = ""
        init_ok = False
        command = "chat"
        parser_retry_count = 0

        while True:
            if parser_retry_count > self.retry_max:
                print("-"*20, "MAX RETRY COUNTS", "-"*20)
                break

            # 如果AI解析失败，就重试
            if ai_said == None:
                command = "redo"
                parser_retry_count += 1
                print("-"*20, "REDO", parser_retry_count, "-"*20)
            else:
                parser_retry_count = 0

            # 用户输入
            if self.task_mode == "auto" and init_ok and command not in ["redo"]:
                # 除第一次，之后都自动回复OK
                command = "ok"
            else:
                # 如果是不是 redo 就获取用户输入；否则直接复用上一次的 user_said 即可
                if command != "redo":
                    _user_said, command = self.ask_user()
                    if _user_said:
                        user_said = _user_said

            print("-"*20, "command:", command, "-"*20)
            # 主动退出
            if command == "quit":
                print("-"*20, "quit" , "-"*20)
                break
                
            elif command == "ok":
                # 生成目录或文件
                if "类型" in ai_said:
                    task_type = ai_said['类型']
                else:
                    print("Error AI Said: ", ai_said)
                    continue

                # 如果确认要生成大纲
                if task_type == "outlines":
                    for item in ai_said['大纲列表']:
                        self.cur_content.add_item(TreeContent(
                            words_advice = item['总字数要求'],
                            title = item['标题名称'],
                            summarise = item['内容摘要'],
                            is_completed = False,
                        ))
                    print("-"*20, "Outlines Done for", self.cur_content.id, "-"*20)
                elif task_type == "paragraph":
                    self.cur_content.text = ai_said['内容']
                    self.cur_content.words_advice = ai_said['总字数要求'],
                    self.cur_content.is_completed = True
                    print("-"*20, "Paragraph Done for", self.cur_content.id, "-"*20)
                else:
                    print("Error JSON: ", ai_said)
                    continue
                
                # 生成子任务后，提纲自身的任务就算完成了
                if self.cur_content.type == None:
                    self.cur_content.type = ai_said['类型']
                if self.cur_content.title == None:
                    self.cur_content.title = user_said
                if self.cur_content.words_advice == None:
                    self.cur_content.words_advice = ai_said['总字数要求']
                self.cur_content.is_completed = True

                # 获取下一个任务的计划
                next_todo = self.root_content.next_todo()
                if next_todo:
                    # 如果下一个任务存在，继续转移到新的任务主题
                    print("-"*20, "Next TODO for ", next_todo.id, "-"*20)
                    self.cur_content = next_todo
                    user_said = f'请帮我扩写《{next_todo.title}》，内容摘要为：{next_todo.summarise}, 字数约为{next_todo.words_advice}字'
                    print("👤[auto]: ", user_said)
                    chain = self.get_chain()
                else:
                    # 如果没有下一个任务，就结束
                    print("-"*20, "Task Complete!", "-"*20)
                    break
                
            if len(user_said) > 0:
                # 如果根文档内容为空，就采纳用户输入的第一句不为特定
                if self.root_content.text == None:
                    self.root_content.text = user_said
                    
                # AI推理
                print("-"*20, "AI for", self.cur_content.id, "-"*20)
                try:
                    if self.streaming:
                        for ai_said in chain.stream(user_said):
                            print(ai_said, flush=True)
                    else:
                        ai_said = chain.invoke(user_said)
                        print(ai_said)
                except Exception as e:
                    print(f"推理错误: {e}")
                    ai_said = None

                # 等到AI开始有正确的返回，才算完成初始化
                if ai_said and '类型' in ai_said and '总字数要求' in ai_said:
                    init_ok = True

            print("-"*20, "All Todos Left", "-"*20)
            print(self.root_content.all_todos())
