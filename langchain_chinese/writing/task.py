from typing import Any, Dict, Iterator, List, Optional, Union
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

_ROOT_FORMAT = """
例如：（假设规定的最大字数限制是300字，那么：
用户要求字数1500字左右，此时超出了300字的写作限定，你必须输出“写作提纲”，可以分为5个部份，每部份约300字左右；
用户要求字数80字左右，此时符合300字左右的限定，你必须输出为“段落内容”。

你必须按照如下格式输出（请务必符合JSON语法限定，以便我能够正确解析）：
```json
{
    "类型": "root",
    "标题名称": 不带编号的标题名称,
    "扩写指南": 可以包含涉及的人物、地点、情节等实体名称和背景设定,
    "总字数要求": 预计的总体字数要求（int类型）
}
```

"""

OUTLINE_MAIN = """
你是一名优秀的写手，可以构思写作思路、扩展写作提纲、细化段落内容，

请务必记住：
1. 当你收到新的写作任务，你应当做两种选择，要么输出写作提纲，要么输出细化的写作内容。
2. 你每次输出的内容规定为最大不超过{{words_limit}}字，因此你必须严格按照如下规则决定该如何输出：
（1）如果发现用户要求的字数超出了最大限制，你就必须输出写作提纲，以便将写作任务拆解，将字数要求分散在提纲列表中。
（2）反之，如果你发现用户要求的字数不超过限制，你就必须输出段落内容。
（3）如果你决定输出写作提纲，那么大纲数量必须大于2，否则还是直接输出为段落内容。
3. 当你输出JSON内容时请特别注意，列表最后一项之后一定不能带有标点符号，这会引起解析错误。
4. 内容摘要：如果你的输出中出现实体名称、创作设定等，就将其单独提炼到内容摘要，
   这样做非常必要，可以让分散多次的创作保持人物、地点、设定等一致。


如果你决定输出“写作提纲”，就请严格按如下格式输出JSON：
{{outline_format}}

如果你决定输出“段落内容”，就请严格按如下格式输出JSON：
{{paragraph_format}}

不要输出JSON以外的内容。
"""

PARAGRAPH_MAIN = """
你是一名优秀的写手，负责详细构思段落细节。
请务必记住：
1. 当你输出JSON内容时请特别注意，列表最后一项之后一定不能带有标点符号，这会引起解析错误。
2. 内容摘要：如果你的输出中出现实体名称、创作设定等，就将其单独提炼到内容摘要，
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

    # 控制参数
    words_per_step = 500
    words_all_limit = 1000
    retry_max = 5

    # - 子任务可能的配置分为：
    # - auto 全部自动回复 OK
    # - redo 已有内容全部重新创作，但用户全部自动回复 OK 
    # - redon 未来可支持 Redo N 次，由 LLM 代替用户做最多 N 次评估
    # - askme 每一步骤都要求用户确认
    # - skip 可以跳过处理，采纳原有的结果或暂时不处理
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
        self.root_content = TreeContent()
        self.cur_content = self.root_content

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
                
        print("task_mode:", self.task_mode)
    
    def print_lines(self, numbers: List[int] = []) -> List[Dict[str, Union[str, int]]]:
        self.root_content.print_lines(numbers)
    
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

        # 确定主提示语模板的类型
        words = self.cur_content.words_advice
        prompt_type = "outline" if words == None or words > self.words_per_step else "paragraph"
        
        # 获取背景信息
        outline = self.root_content.get_outlines()
        
        # 构造基础示语模板
        prompt = ChatPromptTemplate.from_messages([
            ("system", OUTLINE_MAIN if prompt_type == "outline" else PARAGRAPH_MAIN),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{{question}}。请注意，之前的写作提纲为: {{outline}}，你现在的写作任务是上面提纲的一部份")
        ], template_format="jinja2").partial(
            words_limit=self.words_all_limit,
            outline=outline,
            paragraph_format=_PARAGRAPH_FORMAT,
        )        

        # 补充输出格式
        if prompt_type == "outline":
            prompt = prompt.partial(outline_format=_OUTLINE_FORMAT)
        
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
        """生成内容，包括大纲或文件"""
        
        if "类型" in request:
            task_type = request['类型']
        else:
            raise(BaseException("Error AI Said: ", request))

        # 如果确认要生成大纲
        if task_type == "outline":
            self.cur_content.children = []
            for item in request['大纲列表']:
                self.cur_content.add_item(TreeContent(
                    words_advice = item['总字数要求'],
                    title = item['标题名称'],
                    howto = item['扩写指南'],
                    is_completed = False,
                ))
            print("-"*20, "Outlines Done for", self.cur_content.id, "-"*20)
        elif task_type == "paragraph":
            self.cur_content.summarise = request['内容摘要']
            self.cur_content.text = request['详细内容']
            print("-"*20, "Paragraph Done for", self.cur_content.id, "-"*20)
        else:
            raise(BaseException("Error JSON:", request))
        
        # 生成子任务后，提纲自身的任务就算完成了
        self.cur_content.type = task_type
        # self.cur_content.words_advice = ai_said['总字数要求'],
        # self.cur_content.title = ai_said['标题名称'],
        self.cur_content.is_completed = True
    
    def prepare(self):
        """由AI驱动准备背景资料"""
        pass

    def run(self, llm: Runnable = None):
        """由AI驱动展开写作"""
        # 初始化链
        chain = self.get_chain(llm)
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
                    user_said = f'请帮我扩写《{next_todo.title}》, 字数约为{next_todo.words_advice}字，扩写依据为：{next_todo.howto}'
                    print("👤[auto]: ", user_said)
                    chain = self.get_chain(llm)
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
