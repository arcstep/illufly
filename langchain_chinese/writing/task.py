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
from .prompts.task_prompt import *
import json
import re

def get_input(prompt: str = "\n👤: ") -> str:
    return input(prompt)

class WritingTask(BaseModel):
    """
    写作管理。
    
    DONE:
    - 支持一键直出长文
    - 支持询问模式
    - 支持将大纲作为提示语变量
    - 支持将创作中的实体、背景设定作为扩写依据
    - 支持各种状态查询命令
    - 支持大纲导出
    - 支持文字导出

    TODO:
    - 改进子任务对话时的指令跟随能力：强调标题背景
    - 支持在子任务对话中的其他聊天场景：非写作对话
    - 编辑和扩展input中的提示语变量
    - 编辑和扩展全局的提示语变量

    - 支持对日志输出着色

    - 支持移动游标：到根、下一个、上一个、特定位置
    - 支持重写：将已完成状态改为未完成
    - 支持重新确认：不必自动寻找下一个

    - 序列化和反序列化

    - 支持导出到模板库
    - 支持从模板库加载模板

    - 支持提炼并优化提纲模板
    - 支持长文改写

    - 支持精确拆解提纲模板
    - 支持仿写

    - 支持本地知识库检索

    - 支持数据查询

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
            self.root_content = TreeContent(id="root", type="root")                
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
    
    def ask_user(self) -> tuple:
        """捕获用户的输入"""
        
        max_count = 1e3
        counter = 0
        while(counter < max_count):
            counter += 1
            
            resp = get_input()
            content = None
            command = None
            
            commands = [
                "quit",
                "ok",
                "all",
                "todos",
                "todo",
                "focus",
                "memory",
                "memory_store",
            ]

            for cmd in commands:
                if re.search(f'^{cmd}\s*', resp):
                    command = cmd
                    break
            if command == None:
                # 如果用户没有输入有意义的字符串，就重来
                if len(resp) < 2:
                    continue
                command = "chat"
        
            return resp, command

    def get_content_type(self):
        if self.focus == "root@input":
            return "root"
        elif self.cur_content.words_advice > self.words_per_step:
            return "outline"
        else:
            return "paragraph"

    def get_chain(self, llm: Runnable = None):
        """构造Chain"""
        
        # 获取内容类型
        content_type = self.get_content_type()
        # 获取背景信息
        outline_exist = self.root_content.get_outlines()
        
        # 构造基础示语模板
        if content_type == "root":
            task_prompt = _ROOT_TASK
            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{question}}。")
            ], template_format="jinja2").partial(
                # 任务指南
                task_instruction=task_prompt,
                # 输出格式要求
                output_format=_ROOT_FORMAT,
                # JSON严格控制
                json_instruction=_JSON_INSTRUCTION,
            )
        else:
            task_prompt = _OUTLINE_TASK if content_type == "outline" else _PARAGRAPH_TASK
            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
                ("ai", "你对我的写作有什么要求？"),
                ("human", _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{question}}。")
            ], template_format="jinja2").partial(
                # 字数限制
                words_limit=self.words_per_step,
                words_advice=self.cur_content.words_advice,
                # 写作提纲
                title=self.cur_content.title,
                outline_exist=outline_exist,
                # 任务指南
                task_instruction=task_prompt,
                howto=self.cur_content.howto,
                # 输出格式要求
                output_format=_OUTLINE_FORMAT,
                # JSON严格控制
                json_instruction=_JSON_INSTRUCTION,
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
        user_said = f'请帮我扩写'
        print("\n👤:[auto] ", user_said)
        return user_said

    def ask_ai(self, chain: Runnable, question: str):
        """AI推理"""
        
        json = None
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
            if json:
                return json
            
        raise Exception(f"AI返回结果无法正确解析，已经超过 {self.retry_max} 次，可能需要调整提示语模板了！！")
    
    def update_content(self, request: Dict[str, Any] = {}):
        """更新当前内容"""
        
        content_type = self.get_content_type()
        self.cur_content.type = content_type
        
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
            if content_type == "outline":
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
                # print("-"*20, "Outlines Done for", self.cur_content.id, "-"*20)
            elif content_type == "paragraph":
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

    def get_memory(self, id=None):
        if id == None:
            id = self.cur_content.id
        return self.memory.get_shorterm_memory(id).chat_memory.messages

    def print_text(self):
        self.root_content.print_text()
        
    def print_focus(self):
        if self.focus:
            print("-"*20, self.focus, "-"*20)
        
    def print_todos(self):
        """打印todo清单"""

        if self.focus:
            print("-"*20, "Todos", "-"*20)
            for x in self.root_content.todos():
                if x['words_advice'] and x['title']:
                    print(f"* <{x['id']}> {x['words_advice']}字以内 | 《{x['title']}》")
                else:
                    print(f"* <{x['id']}>")
        else:
            # 如果没有下一个任务，就结束
            print("-"*20, "Done!", "-"*20)

    def print_all(self):
        """打印所有清单"""

        print("-"*20, "All", "-"*20)
        for x in self.root_content.all():
            if x['words_advice'] and x['title']:
                print(f"{' ' if x['is_completed'] else '*'} <{x['id']}> {x['words_advice']}字以内 | 《{x['title']}》")
            else:
                print(f"{' ' if x['is_completed'] else '*'} <{x['id']}>")

    def run(self, task: str = None, llm: Runnable = None):
        """由AI驱动展开写作"""

        # 处理进度
        self.print_todos()

        # 
        chain = self.get_chain(llm)
        ai_said = {}
        user_said = ""
        command = "chat"
        
        if task:
            # 如果参数中提供了初始化的任务描述，就直接采纳
            user_said = task
        else:
            if self.focus.endswith("@output"):
                # 如果是断点任务重新开始，就从当前节点的output开始
                user_said = self.output_user_auto_said()
            else:
                # 否则就先询问用户
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

            # print("-"*20, "command:", command, "-"*20)
            # 主动退出
            if command == "quit":
                print("-"*20, "quit" , "-"*20)
                break

            # 查看所有任务
            elif command == "all":
                self.print_all()
                continue

            # 查看待办任务
            elif command == "todos":
                self.print_todos()
                continue

            # 查看当前游标
            elif command == "focus":
                self.print_focus()
                continue

            # 查看记忆
            elif command == "memory":
                print(self.get_memory())
                continue

            # 查看记忆
            elif command == "memory_store":
                print(self.memory._shorterm_memory_store)
                continue

            # 确认当前成果
            elif command == "ok":
                # 尝试更新当前游标指向的内容
                # 如果更新失败，就要退出循环
                self.update_content(request=ai_said)

                # 获取下一个任务的计划
                self.move_focus_auto()
                self.print_todos()
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
                    # 全部结束，打印成果出来瞧瞧
                    self.print_text()
                    break
            else:
                # 其他命令暂时没有特别处理
                pass

            # AI推理
            ai_said = self.ask_ai(chain, user_said)
