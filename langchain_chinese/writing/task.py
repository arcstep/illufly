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
import os

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

    - 改进子任务对话时的指令跟随能力：强调标题背景

    TODO:
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
    # - "START"
    # - "ROOT"
    # - "子内容ID"
    # - "END"
    focus: Optional[str] = "START"
    
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
    ai_reply: Optional[Dict[str, str]] = {}
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
        keys = ["task_mode"]
        for k in keys:
            if k in kwargs:
                setattr(self, k, kwargs[k])

        if self.root_content == None:
            self.root_content = TreeContent(id="ROOT", type="root")                
        self.move_focus("START")

    def move_focus(self, id: str) -> str:
        """
        移动到指定节点，默认将位置设定为output。
        """

        if id == "START":
            self.cur_content = self.root_content
            self.focus = id
        elif id == "END":
            self.focus = id
        else:
            target = self.root_content.get_item_by_id(id)
            self.cur_content = target
            self.focus = self.cur_content.id

        return self.focus

    def move_focus_auto(self) -> str:
        """
        从root开始遍历所有未完成的节点。
        """
        if self.focus == "START":
            self.move_focus(self.cur_content.id)
        else:
            next_todo = self.root_content.next_todo()
            if next_todo:
                self.move_focus(next_todo.id)
            else:
                self.focus = "END"
        return self.focus

    def ask_user(self, user_said: str = None) -> tuple:
        """捕获用户的输入"""
        
        # 最多重新输入100次
        max_count = 100
        counter = 0
        while(counter < max_count):
            counter += 1
            
            resp = user_said if user_said else get_input()
            resp = resp.strip()

            commands = [
                "quit",       # 退出
                "reload",     # 重新加载模型
                "all",        # 所有任务
                "todos",      # 所有待办
                "ok",         # 确认INIT任务，或某ID提纲或段落
                "children",   # 查看某ID提纲
                "words",      # 查看后修改某ID字数
                "title",      # 查看后修改某ID标题
                "howto",      # 查看后修改某ID扩写指南
                "summarise",  # 查看后修改某ID段落摘要
                "move",       # 移动任务到某ID
                "todo",       # 某ID待办，默认当前ID
                "memory",     # 某ID对话记忆，默认当前ID
                "history",    # 某ID对话历史，默认当前ID
                "text",       # 某ID下的文字成果，默认ROOT
            ]

            # 使用正则表达式解析命令
            match_full = re.match(r'^([\w-]+)@([\w-]+)(.*)$', resp)
            match_command = re.match(r'^([\w-]+)(.*)$', resp)
            
            id, command, param = None, None, None
            
            if match_full:
                id, command, param = match_full.groups()
            elif match_command:
                id = None
                command, param = match_command.groups()

            param = param.strip()  # 去除参数前后的空格
            if command in commands:
                return id, command, param
            elif len(resp) <= 0:
                # 如果用户没有输入有意义的字符串，就重来
                continue
            else:
                return None, "ask", resp
            
        return None, None, None

    def user_said_continue(self) -> (str, str):
        """用户确认继续生成"""
        
        user_said = f'请开始！'
        # print("\n👤:[auto] ", user_said)
        return user_said

    def update_chain(self, llm: Runnable = None):
        """构造Chain"""
        
        # 获取内容类型
        content_type = self.get_content_type()
        
        # 构造基础示语模板
        json_instruction = _JSON_INSTRUCTION
        
        if content_type == "START":
            task_prompt   = _ROOT_TASK
            output_format = _ROOT_FORMAT
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
                ("ai", "好的，我将严格按要求的JSON格式输出。"),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{task}}"),
            ], template_format="jinja2").partial(
                # 任务指南
                task_instruction=task_prompt,
                # 输出格式要求
                output_format=output_format,
                # JSON严格控制
                json_instruction=json_instruction,
            )
        else:
            # 获取背景信息
            outline_exist = self.root_content.get_outlines()

            if content_type == "outline":
                task_prompt   = _OUTLINE_TASK
                output_format = _OUTLINE_FORMAT
            else:
                task_prompt   = _PARAGRAPH_TASK
                output_format = _PARAGRAPH_FORMAT

            prompt = ChatPromptTemplate.from_messages([
                ("system", MAIN_PROMPT),
                ("ai", "你对我的写作有什么要求？"),
                ("human", _AUTO_OUTLINE_OR_PARAGRAPH_PROMPT),
                ("ai", "好的，我将严格按要求的JSON格式输出。"),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{{task}}")
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
                output_format=output_format,
                # JSON严格控制
                json_instruction=json_instruction,
            )

        # 默认选择智谱AI
        if llm == None:
            if os.environ.get("ZHIPUAI_API_KEY") == None:
                raise BaseException("您正在尝试在 langchain_chinese 中使用智谱AI，请在环境变量 ZHIPUAI_API_KEY 中提供 APIKEY！")
            llm = ChatZhipuAI()

        # 构造链
        chain = prompt | llm
        # print(prompt.format(task="<<DEMO_TASK>>", history=[]))

        # 记忆绑定管理
        withMemoryChain = WithMemoryBinding(
            chain,
            self.memory,
            input_messages_key="task",
            history_messages_key="history",
        )
        
        return withMemoryChain

    def ask_ai(self, chain: Runnable, task: str):
        """AI推理"""

        json = None
        counter = 0
        while(counter < self.retry_max):
            counter += 1
            try:
                input = {"task": task}
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
                self.ai_reply = json
                return json

        raise Exception(f"AI返回结果无法正确解析，已经超过 {self.retry_max} 次，可能需要调整提示语模板了！！")
    
    def get_content_type(self):
        if self.focus == "START":
            return "START"
        elif self.focus == "END":
            return None
        else:
            if self.cur_content.words_advice > self.words_per_step:
                return "outline"
            else:
                return "paragraph"

    def update_content(self):
        """
        更新当前内容。

        如果是任务初始状态，应当包含：
            - 标题名称
            - 总字数要求
            - 扩写指南
            - 内容摘要

        如果是提纲，提纲中的元素应当包含：
            - 大纲列表
                - 总字数要求
                - 标题名称
                - 扩写指南

        如果是段落，应当包含：
            - 详细内容
            - 内容摘要
        """
        request = self.ai_reply 
        content_type = self.get_content_type()
        self.cur_content.type = content_type
        
        if content_type == "START":
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
        elif content_type == "END":
            return
        else:
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

    def get_memory(self, id=None):
        if id == None:
            id = self.cur_content.id
        return self.memory.get_shorterm_memory(id).chat_memory.messages

    def print_text(self):
        self.root_content.print_text()
        
    def print_focus(self):
        print(f"{self.focus}@")
        
    def print_todos(self):
        """打印todo清单"""

        if self.focus:
            print("-"*20, "TODOs", "-"*20)
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

    def run(self, input: str = None, llm: Runnable = None, task_mode = None, max_steps = 1e4):
        """
        由AI驱动展开写作。
        
        from langchain_chinese import WritingTask
        wp = WritingTask()

        支持如下场景：
        - 给定任务，自动开始
        w.run(
            input = "请帮我写一封道歉信"
            task_mode = "auto"
        )

        - 未定任务，获取第一次输入，自动开始        
        w.run(
            task_mode = "auto"
        )

        - 给定任务，每次询问
        w.run(
            input = "请帮我写一封道歉信"
            task_mode = "askme"
        )

        - 未定任务，每次询问
        w.run(
            task_mode = "askme"
        )

        - 询问模式退出前，尚在初始阶段

        - 询问模式退出前，有任务待确认
        - 询问模式退出前，任务已确认
        - 询问模式接续后，转自动
        - 仅对大纲自动模式，段落手动模式

        - 每一步执行后都直接退出（不做循环）
          max_steps = 1 即可
        """
        
        # 更新任务模式
        if task_mode:
            self.task_mode = task_mode

        # 打印处理进度
        self.print_focus()
        self.print_todos()

        # 初始化链
        chain = self.update_chain(llm)
        
        # 最多允许步数的限制
        counter = 0
        command = None
        param = None

        while(counter < max_steps):
            counter += 1

            if self.ai_reply == {}:
                # 新任务
                id, command, param = self.ask_user(input)
            else:
                # 跟踪之前状态的任务
                if self.task_mode == "auto":
                    id, command, param = self.ask_user("ok")
                else:
                    id, command, param = self.ask_user(input)

            # 无效命令过滤
            if input and command == "ok" and self.ai_reply == {}:
                input = None
                continue
            
            # 输入重置
            input = None
            print(f"{self.focus}@{command}")

            # 主动退出
            if command == "quit":
                break

            # 查看字数建议
            elif command == "words":
                print(self.cur_content.words_advice)
                continue

            # 查看标题
            elif command == "title":
                print(self.cur_content.title)
                continue

            # 查看扩写指南
            elif command == "howto":
                print(self.cur_content.howto)
                continue

            # 查看内容摘要
            elif command == "summarise":
                print(self.cur_content.summarise)
                continue

            # 查看所有任务
            elif command == "children":
                print(self.cur_content.children)
                continue
            
            # 查看所有任务
            elif command == "all":
                self.print_all()
                continue

            # 查看待办任务
            elif command == "todos":
                self.print_todos()
                continue

            # 查看当前游标
            elif command == "todo":
                self.print_focus()
                continue

            # 查看记忆
            elif command == "memory":
                print(self.get_memory())
                continue

            # 查看记忆
            elif command == "store":
                print(self.memory._shorterm_memory_store)
                continue

            # 查看成果
            elif command == "text":
                self.print_text()
                continue
            
            # 重新加载
            # 在更新提示语模板、变量之后
            elif command == "reload":
                print("已经更新访问AI的参数配置")
                chain = self.update_chain(llm)
                continue

            # 确认当前成果
            elif command == "ok":
                # 尝试更新当前游标指向的内容
                # 如果更新失败，就要退出循环
                self.update_content()

                # 获取下一个任务的计划
                self.move_focus_auto()
                self.print_todos()
                if self.focus == "START":
                    pass
                elif self.focus == "END":
                    # 全部结束，打印成果出来瞧瞧
                    self.print_text()
                    break
                else:
                    # 如果下一个任务存在，继续转移到新的扩写任务
                    param = self.user_said_continue()
                    # 如果不移动任务游标，就一直使用这个chain
                    chain = self.update_chain(llm)
            elif command == "ask":
                pass
            else:
                # 其他命令暂时没有特别处理
                print("UNKOWN COMMAND:", command)

            # AI推理
            self.ask_ai(chain, param)
