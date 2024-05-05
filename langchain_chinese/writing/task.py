from typing import Any, Dict, Iterator, List, Optional, Union
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain_zhipu import ChatZhipuAI
from langchain_core.runnables import Runnable
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
3. 当你输出JSON内容时请特别注意，列表最后一项之后一定不能带有标点符号，这会引起解析错误。

例如：
用户要求字数1500字左右，此时超出了300字的写作限定，你必须输出“写作提纲”，可以分为5个部份，每部份约300字左右；
用户要求字数80字左右，此时符合300字左右的限定，你必须输出为“段落内容”。

如果你决定输出“写作提纲”，就请按照如下格式输出写作大纲：
```json
{
    "类型": "outline",
    "标题名称": 标题名称,
    "内容摘要": 内容摘要,
    "总字数要求": 预计的总体字数要求（int类型）,
    "大纲数量": 与以上列表相符的大纲数量,
    "大纲列表": [
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要},
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要},
        {"标题名称": "标题名称", "总字数要求": 段落的字数要求（int类型）, "内容摘要": 内容摘要},
        ...
    ]
}
```

如果你决定输出“段落内容”，就请按照如下格式输出：
```json
{
    "类型": "paragraph",
    "标题名称": 标题名称,
    "内容摘要": 内容摘要,
    "总字数要求": 段落的字数要求（int类型）,
    "内容": 你的详细输出
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
    "标题名称": 标题名称,
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

    # - 子任务可能的配置分为：
    # - auto 全部自动回复 OK
    # - redo 已有内容全部重新创作，但用户全部自动回复 OK 
    # - redon 未来可支持 Redo N 次，由 LLM 代替用户做最多 N 次评估
    # - askme 每一步骤都要求用户确认
    # - skip 可以跳过处理，采纳原有的结果或暂时不处理
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

    def ask_user(self) -> tuple:
        """捕获用户的输入"""
        
        max_count = 1e3
        counter = 0
        while(counter < max_count):
            counter += 1
            
            resp = get_input()
            content = None
            command = None
        
            if(resp == "quit"):
                command = "quit"
            elif(resp == "ok"):
                command = "ok"
            else:
                # 如果用户没有输入有意义的字符串，就重来
                if command == None and len(resp) < 2:
                    continue
                content = resp
                command = "chat"
        
            return content, command

    def get_chain(self):
        """构造Chain"""
        
        words = self.cur_content.words_advice
        if words == None or words > self.words_per_step:
            instruction = OUTLINE_INSTRUCTIONS
        else:
            instruction = PARAGRAPH_INSTRUCTIONS
        
        prompt_init = ChatPromptTemplate.from_messages([
            ("system", instruction),
            ("user", "{{question}}")
        ], template_format='jinja2')

        prompt_detail = ChatPromptTemplate.from_messages([
            ("system", instruction),
            ("assistant", "之前的写作提纲为: {{outline}}"),
            ("user", "{{question}}。请注意，你现在的写作任务是上面已有提纲的一部份")
        ], template_format='jinja2')

        return (prompt_init | ChatZhipuAI() | JsonOutputParser())

    def ask_ai(self, chain: Runnable, question: str):
        """AI推理"""
        
        resp = None
        print("-"*20, "AI for", self.cur_content.id, "-"*20)
        counter = 0
        while(counter < self.retry_max):
            counter += 1
            try:
                if self.streaming:
                    for resp in chain.stream({"question": question}):
                        print(resp, flush=True)
                else:
                    resp = chain.invoke({"question": question})
                    print("resp:", resp)
            except Exception as e:
                print(f"推理错误: {e}")
            
            # 允许重试N次，满足要求后才返回AI的回应
            if resp and '类型' in resp and '总字数要求' in resp:
                return resp
            
        raise Exception(f"大模型解析错误已经超过 {self.retry_max} 次，看来暂时无法工作了！！")
    
    def update_content(self, ai_said: Dict[str, Any]):
        """生成内容，包括大纲或文件"""
        
        if "类型" in ai_said:
            task_type = ai_said['类型']
        else:
            raise(BaseException("Error AI Said: ", ai_said))

        # 如果确认要生成大纲
        if task_type == "outline":
            self.cur_content.children = []
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
            print("-"*20, "Paragraph Done for", self.cur_content.id, "-"*20)
        else:
            raise(BaseException("Error JSON:", ai_said))
        
        # 生成子任务后，提纲自身的任务就算完成了
        self.cur_content.type = task_type
        # self.cur_content.words_advice = ai_said['总字数要求'],
        # self.cur_content.title = ai_said['标题名称'],
        self.cur_content.is_completed = True

    def run(self):
        # 初始化链
        chain = self.get_chain()
        ai_said = {}
        user_said = ""
        init_ok = False
        command = "chat"
        parser_retry_count = 0

        max_count = 1e4
        counter = 0
        while(counter < max_count):
            counter += 1

            # 用户输入
            if init_ok and self.task_mode == "auto":
                # 除第一次，之后都自动回复OK
                command = "ok"
            elif self.task_mode == "askme":
                # 否则获取用户输入
                user_said, command = self.ask_user()
            else:
                # 其他模式暂不支持，全部视为 askme
                user_said, command = self.ask_user()

            print("-"*20, "command:", command, "-"*20)
            # 主动退出
            if command == "quit":
                print("-"*20, "quit" , "-"*20)
                break
                
            elif command == "ok":
                # 尝试更新当前游标指向的内容
                try:
                    self.update_content(ai_said)
                except BaseException as e:
                    print(e)
                    continue

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
            else:
                # 其他命令暂时没有特别处理
                pass

            # AI推理
            ai_said = self.ask_ai(chain, user_said)
            init_ok = True

            # 处理进度
            print("-"*20, "Todos Left", "-"*20)
            for x in self.root_content.all_todos():
                print(x['id'], "| words:", x['words_advice'])
