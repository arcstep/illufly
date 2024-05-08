from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain_zhipu import ChatZhipuAI
from langchain_core.runnables import Runnable
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding
from .content import TreeContent
import json
import re

_ROOT_FORMAT = """
（请确保输出符合JSON语法限定，以便我能够正确解析）
```json
{
    "类型": "root",
    "标题名称": 根据写作任务，给出用户要求或你推荐的标题名称，不要带编号
    "扩写指南": 应当尽量包含写作任务中提及的写作要求，也可以包含你的创作建议中所涉及的人物、地点、情节等实体名称和背景设定,
    "总字数要求": 预计的总体字数要求（int类型），默认为1000字。
}
```
"""

_OUTLINE_FORMAT = """
（请确保输出符合JSON语法限定，以便我能够正确解析）
```json
{
    "类型": "outline",
    "标题名称": 收到扩写任务时要求的标题,
    "大纲列表": [
        {
            "总字数要求": 段落的字数要求（int类型）,
            "标题名称": 不带编号的标题名称,
            "扩写指南": 可以包含涉及的人物、地点、情节等实体名称和背景设定
        },
        ...,
        {
            "总字数要求": 段落的字数要求（int类型）,
            "标题名称": 不带编号的标题名称,
            "扩写指南": 可以包含涉及的人物、地点、情节等实体名称和背景设定
        }
    ]
}
```
"""

_PARAGRAPH_FORMAT = """
（请确保输出符合JSON语法限定，以便我能够正确解析）
```json
{
    "类型": "paragraph",
    "标题名称": 收到扩写任务时要求的标题,
    "详细内容": "你的详细输出",
    "内容摘要": 详细内容提要，可以包括涉及的人物、地点、情节等实体名称和背景设定
}
```
"""

ROOT_MAIN = """
你是一名优秀的写手，任务是对写作任务做评估，给出总体写作建议。

请严格按如下格式输出JSON：
{{root_format}}

不要输出JSON以外的内容。
"""

OUTLINE_MAIN = """
你是一名优秀的写手，可以构思写作思路、扩展写作提纲。

请务必记住：
1. 如果你的创作建议中出现实体名称、创作设定等，就将其单独提炼到扩写指南，
   这样做非常必要，可以让分散多次的创作保持人物、地点、设定等一致。
2. 你在拆分提纲时，每个子任务的字数要求不要低于200字。

请严格按如下格式输出JSON：
{{outline_format}}

不要输出JSON以外的内容。
"""

PARAGRAPH_MAIN = """
你是一名优秀的写手，负责详细构思段落细节。
请务必记住：
1. 如果你的创作建议中出现实体名称、创作设定等，就将其单独提炼到内容摘要，
   这样做非常必要，可以让分散多次的创作保持人物、地点、设定等一致。

请严格按如下格式输出JSON：
{{paragraph_format}}

不要输出JSON以外的内容。
"""

def get_input(prompt: str = "\n👤: ") -> str:
    return input(prompt)

class WritingTask(BaseModel):
    """
    写作管理。
    """
    root_content: Optional[TreeContent] = None
    cur_content: Optional[TreeContent] = None

    # 创作游标 forcus 取值范围为：
    # - "root@input"
    # - "root@output"
    # - "内容对象@input"
    # - "内容对象@output"
    #
    # 默认的自动创作路径应当是：
    # root@input -> root@output -> 内容对象@output
    focus: Optional[str] = "root@input"
    
    # 控制参数
    words_per_step = 500
    retry_max = 5

    # - 子任务可能的配置分为：
    # - auto 全部自动回复 OK
    # - askme 每一步骤都要求用户确认
    task_mode = "askme"

    task_title: Optional[str] = None
    task_howto: Optional[str] = None

    streaming = True

    # 记忆管理
    memory: Optional[MemoryManager] = None

    class Config:
        arbitrary_types_allowed = True  # 允许任意类型

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 短期记忆体
        self.memory = MemoryManager(
            # 暂不考虑保存对话历史到磁盘
            # lambda session_id: LocalFileMessageHistory(session_id),
            shorterm_memory = ConversationBufferWindowMemory(return_messages=True, k=20)
        )

        # 初始化参数
        keys = ["task_mode", ""]
        for k in keys:
            if k in kwargs:
                setattr(self, k, kwargs[k])
        print("Task Mode:", self.task_mode)

        if self.root_content == None:
            self.root_content = TreeContent(id="root")                
        self.move_focus("root", pos="input")
        print("Focus from:", self.focus)

    def move_focus(self, id: str, pos: str="output") -> Tuple[TreeContent, str]:
        """
        移动到指定节点，默认将位置设定为output。
        """
        target = self.root_content.get_item_by_id(id)
        self.cur_content = target
        self.focus = f"{self.cur_content.id}@{pos}"
        return self.cur_content, self.focus

    def move_focus_auto(self) -> str:
        """
        从root开始遍历所有未完成的节点。
        """
        if self.focus.endswith("@input"):
            self.move_focus(self.cur_content.id, pos="output")
        else:
            next_todo = self.root_content.next_todo()
            if next_todo:
                self.move_focus(next_todo.id, pos="output")
            else:
                self.focus = None
        return self.focus
    
    def print_text(self) -> List[Dict[str, Union[str, int]]]:
        self.root_content.print_text()
    
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

    def get_chain(self, llm: Runnable = None):
        """构造Chain"""
        
        # 获取提示语类型
        if self.focus == "root@input":
            prompt_type = "root"
        elif self.cur_content.words_advice > self.words_per_step:
            prompt_type = "outline"
        else:
            prompt_type = "paragraph"

        # 获取背景信息
        outline = self.root_content.get_outlines()
        
        # 构造基础示语模板
        if prompt_type == "root":
            prompt = ChatPromptTemplate.from_messages([
                ("system", ROOT_MAIN),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{question}}。")
            ], template_format="jinja2").partial(
                root_format=_ROOT_FORMAT,
            )
        elif prompt_type == "outline":
            prompt = ChatPromptTemplate.from_messages([
                ("system", OUTLINE_MAIN),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{question}}。请注意，总体写作提纲为: {{outline}}，你现在的写作任务是其中的一部份")
            ], template_format="jinja2").partial(
                words_limit=self.words_per_step,
                outline=outline,
                paragraph_format=_PARAGRAPH_FORMAT,
                outline_format=_OUTLINE_FORMAT,
            )
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", PARAGRAPH_MAIN),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{question}}。请注意，总体写作提纲为: {{outline}}，你现在的写作任务是其中的一部份")
            ], template_format="jinja2").partial(
                words_limit=self.words_per_step,
                outline=outline,
                paragraph_format=_PARAGRAPH_FORMAT,
            )

        # 默认选择智谱AI
        if llm == None:
            llm = ChatZhipuAI()

        # 构造链
        chain = prompt | llm

        # 记忆绑定管理
        withMemoryChain = WithMemoryBinding(
            chain,
            self.memory,
            input_messages_key="question",
            history_messages_key="history",
        )
        
        return withMemoryChain

    def output_user_auto_said(self) -> str:
        user_said = f'请帮我扩写《{self.cur_content.title}》, 字数不超过{self.cur_content.words_advice}字，扩写依据为：{self.cur_content.howto}'
        print("👤[auto]: ", user_said)
        return user_said

    def ask_ai(self, chain: Runnable, question: str):
        """AI推理"""
        
        json = None
        print("-"*20, "AI for", self.cur_content.id, "-"*20)
        counter = 0
        while(counter < self.retry_max):
            counter += 1
            try:
                input = {"question": question}
                config = {"configurable": {"session_id": self.cur_content.id}}
                text = ""
                if self.streaming:
                    for resp in chain.stream(input, config=config):
                        print(resp.content, end="", flush=True)
                        text += resp.content
                    print()
                else:
                    resp = chain.invoke(input, config=config)
                    print("resp:", resp.content)
                    text = resp.content

                json = JsonOutputParser().invoke(input=text)
            except Exception as e:
                print(f"推理错误: {e}")
            
            # 允许重试N次，满足要求后才返回AI的回应
            if json and '类型' in json:
                return json
            
        raise Exception(f"大模型解析错误已经超过 {self.retry_max} 次，看来暂时无法工作了！！")
    
    def update_content(self, request: Dict[str, Any] = {}):
        """更新当前内容"""
        
        if "类型" in request:
            task_type = request['类型']
            self.cur_content.type = task_type
        else:
            raise(BaseException("Error AI Said: ", request))
        
        if self.focus.endswith("@input"):
            # 更新生成依据
            try:
                self.cur_content.title = request["标题名称"]
                self.cur_content.words_advice = request["总字数要求"]
            except BaseException as e:
                print(self.focus, "缺少必要的字段：标题名称 | 总字数要求")
                raise(e)

            if "扩写指南" in request:
                self.cur_content.howto = request["扩写指南"]
            if "内容摘要" in request:
                self.cur_content.summarise = request["内容摘要"]
        elif self.focus.endswith("@output"):
            # 更新生成大纲或详细内容
            if task_type == "outline":
                self.cur_content.children = []
                for item in request['大纲列表']:
                    if "总字数要求" not in item or "标题名称" not in item or "扩写指南" not in item:
                        raise(BaseException("缺少必要的字段：标题名称 | 总字数要求 | 扩写指南"))
                    self.cur_content.add_item(TreeContent(
                        words_advice = item['总字数要求'],
                        title = item['标题名称'],
                        howto = item['扩写指南'],
                        is_completed = False,
                    ))
                print("-"*20, "Outlines Done for", self.cur_content.id, "-"*20)
            elif task_type == "paragraph":
                if "内容摘要" in request:
                    self.cur_content.summarise = request["内容摘要"]
                if "详细内容" in request:
                    self.cur_content.text = request["详细内容"]
            else:
                raise(BaseException("Error JSON:", request))
            
            # 生成子任务后，提纲自身的任务就算完成了
            self.cur_content.is_completed = True
        else:
            raise(BaseException("Error FOCUS:", self.focus))
    
    def run(self, llm: Runnable = None):
        """由AI驱动展开写作"""
        # 
        chain = self.get_chain(llm)
        ai_said = {}
        user_said = ""
        command = "chat"

        if self.focus == "root@input":
            # 如果任务还没有确认，就需要询问用户
            user_said, command = self.ask_user()
            ai_said = self.ask_ai(chain, user_said)

        # 最多允许步数的限制
        max_steps_count = 1e4
        counter = 0
        while(counter < max_steps_count):
            counter += 1

            if self.task_mode == "auto":
                # 自动回复OK
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
                # 如果更新失败，就要退出循环
                self.update_content(request=ai_said)

                # 获取下一个任务的计划
                self.move_focus_auto()
                print("-"*20, "Move To:", self.focus, "-"*20)
                if self.focus:
                    if self.focus.endswith("@output"):
                        # 如果下一个任务存在，继续转移到新的扩写任务
                        user_said = self.output_user_auto_said()
                        # 如果不移动游标，就一直使用这个chain
                        chain = self.get_chain(llm)
                    elif self.focus.endswith("@input"):
                        # 如果进入到属性修改任务
                        print("暂时不支持属性修改任务")
                        break
                else:
                    # 如果没有下一个任务，就结束
                    print("-"*40, "\nAll Complete!")
                    break
            else:
                # 其他命令暂时没有特别处理
                pass

            # AI推理
            ai_said = self.ask_ai(chain, user_said)

            # 处理进度
            print("-"*20, "Todos", "-"*20)
            for x in self.root_content.all_todos():
                print(x['id'], x['words_advice'], "字 |", x['title'])
