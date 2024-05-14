from typing import Any, Dict, Iterator, List, Optional, Union, Tuple
from langchain.pydantic_v1 import BaseModel, Field, root_validator
from langchain_core.runnables import Runnable
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding
from .content import TreeContent
from .command import *
from .prompts.task_prompt import *
import json
import re
import os

def get_input(prompt: str = "\n👤: ") -> str:
    return input(prompt)

_COMMON_COMMANDS = [
    "quit",       # 退出
    "all",        # 所有任务
    "todos",      # 所有待办
    "ask",
]

_AI_CHAT_COMMANDS = [
    "todo",       # 某ID待办，默认当前ID
    "ok",         # 确认START任务，或某ID提纲或段落，然后自动进入下一待办任务
    "reload",     # 重新加载模型
    "memory",     # 某ID对话记忆，默认当前ID
    "store",      # 某ID对话历史，默认当前ID
    "ask",        # 向AI提问
]

_WRITE_COMMANDS = [
    "todo",       # 某ID待办，默认当前ID
    "words",      # 查看后修改某ID字数
    "title",      # 查看后修改某ID标题
    "howto",      # 查看后修改某ID扩写指南
    "summarise",  # 查看后修改某ID段落摘要
    "reload",     # 重新加载模型
]

_READ_COMMANDS = [
    "text",       # 某ID下的文字成果，默认ROOT
    "todo",       # 某ID待办，默认当前ID
    "children",   # 查看某ID提纲
    "words",      # 查看后修改某ID字数
    "title",      # 查看后修改某ID标题
    "howto",      # 查看后修改某ID扩写指南
    "summarise",  # 查看后修改某ID段落摘要
    "memory",     # 某ID对话记忆，默认当前ID
    "store",      # 某ID对话历史，默认当前ID
    "reply",      # AI的当前回复
]


class WritingTask(BaseModel):
    """
    写作管理。
    """
    root_content: Optional[TreeContent] = None
    todo_content: Optional[TreeContent] = None

    # 控制参数
    words_per_step = 500
    retry_max = 5

    # 自动运行模式
    # none | all | outline | paragraph
    auto = "none"

    task_title: Optional[str] = None
    task_howto: Optional[str] = None

    streaming = True

    # 记忆管理
    ai_reply_json: Optional[Dict[str, str]] = {}
    memory: Optional[MemoryManager] = None

    # 任务游标：
    @property
    def default_focus(self):
        return f'{todo_content.id}#{todo_content.default_scope}'

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
        keys = ["auto"]
        for k in keys:
            if k in kwargs:
                setattr(self, k, kwargs[k])

        if self.root_content == None:
            self.root_content = TreeContent(type="root")                
        self.move_focus("START")

    def move_focus(self, focus: str) -> str:
        """
        移动到指定节点，默认将位置设定为output。
        """
        if focus == "START":
            self.todo_content = self.root_content
            self.focus = focus
        elif focus == "END":
            self.todo_content = None
            self.focus = focus
        elif focus == None:
            # 没有解析到内容ID
            pass
        else:
            target = self.root_content.get_item_by_id(focus)
            if target:
                self.todo_content = target
                self.focus = f'{target.id}'
            else:
                # 在对象树中无法找到内容ID
                pass

        return self.focus

    def move_focus_auto(self) -> str:
        """
        从root开始遍历所有未完成的节点。
        """
        if self.focus == "END":
            pass
        elif self.focus == "START":
            self.move_focus(self.todo_content.id)
        else:
            next_todo = self.root_content.next_todo()
            if next_todo:
                self.move_focus(next_todo.id)
            else:
                self.focus = "END"
        return self.focus

    def user_said_continue(self) -> (str, str):
        """用户确认继续生成"""
        
        user_said = f'请开始！'
        print("\n👤:[auto] ", user_said)
        return user_said

    def get_content_type(self):
        if self.focus == "END":
            return None
        elif self.focus == "START":
            return "START"
        else:
            if self.todo_content.words_advice > self.words_per_step:
                return "outline"
            else:
                return "paragraph"

    def get_memory(self, session_id=None):
        if session_id == None:
            session_id = f'{self.focus}'
        return self.memory.get_shorterm_memory(session_id).chat_memory.messages

    def print_text(self):
        self.root_content.print_text()
        
    def print_focus(self):
        print(f"[{self.focus}]")

    def print_todos(self):
        """打印todo清单"""

        if self.focus == "END":
            # 如果没有下一个任务，就结束
            print("-"*20, "Done!", "-"*20)
        else:
            print("-"*20, "TODOs", "-"*20)
            for x in self.root_content.todos():
                sid = f"[{x['id']}]" if self.focus == f"{x['id']}" else f"<{x['id']}>"
                if x['words_advice'] and x['title']:
                    print(f"* {sid} 约{x['words_advice']}字 | 《{x['title']}》")
                else:
                    print(f"* {sid}")

    def print_all(self):
        """打印所有清单"""

        print("-"*20, "All", "-"*20)
        for x in self.root_content.all():
            sid = f"[{x['id']}]" if self.focus == f"{x['id']}" else f"<{x['id']}>"
            if x['words_advice'] and x['title']:
                print(f"{' ' if x['is_completed'] else '*'} {sid} {x['words_advice']}字以内 | 《{x['title']}》")
            else:
                print(f"{' ' if x['is_completed'] else '*'} {sid}")

    # 指令处理函数：查看或修改内容对象的
    def process_content_command(focus, id, k, v):
        # 当前在END节点，没有todo项，且未指定操作对象ID
        if focus == "END":
            obj = None
        # 当前在START节点，且未指定操作对象ID
        elif focus == "START":
            obj = self.root_content
        # 当前在普通节点，且为指定操作对象ID
        elif id == None:
            obj = self.todo_content
        # 已明确指定操作对象ID
        else:
            obj = self.root_content.get_item_by_id(id)

        # 设置内容属性
        if obj and v != None:
            obj.set_prompt_input(k, v)

        # 打印指定对象的指定属性
        if obj:
            print(f'<{focus}> {k:}', obj.get_prompt_input(k))

    def run(self, input: str = None, llm: Runnable = None, auto = None, max_steps = 1e4):
        """
        由AI驱动展开写作。
        """
        
        # 更新任务模式
        if auto:
            self.auto = auto

        # 初始化链
        chain = self.update_chain(llm)

        # 当前todo位置
        self.print_focus()
        
        # 最多允许步数的限制
        counter = 0
        command = None
        prompt = None

        while(counter < max_steps):
            counter += 1

            # 获取用户指令
            focus, id, command, prompt = self.ask_user(input)
            input = None

            if focus == "END":
                obj = None
            # 当前在START节点，且未指定操作对象ID
            elif focus == "START":
                obj = self.root_content
            # 当前在普通节点，且为指定操作对象ID
            elif id == None:
                obj = self.todo_content
            # 已明确指定操作对象ID
            else:
                obj = self.root_content.get_item_by_id(id)

            # 处理用户指令
            command = BaseCommand.create_command(command, obj, prompt)
            #
            # 主动退出
            resp = command.invoke()
            if resp["reply"] == "end":
                break

            # 查看所有任务
            elif command == "all":
                self.print_all()

            # 查看待办任务
            elif command == "todos":
                self.print_todos()

            # 修改或打印当前的待处理任务ID
            elif command == "todo":
                if focus == "END":
                    self.move_focus(focus)
                else:
                    process_content_command('is_completed', False)
                    if focus != self.focus:
                        memory = self.get_memory(session_id=focus)
                        if len(memory) > 0:
                            self.ai_reply_json = JsonOutputParser().invoke(input=memory[-1])
                        else:
                            self.ai_reply_json = {}
                        self.move_focus(focus)

                        # 修改了内容目标，所以重新生成LLM链
                        chain = self.update_chain(llm)
                self.print_focus()

            # 询问AI
            elif command == "ask":
                if not prompt:
                    prompt = "请重新生成"
                self.ask_ai(chain, prompt)
            
            # 获取AI回复
            elif command == "reply":
                memory = self.get_memory(session_id=focus)
                if len(memory) > 0:
                    print(memory[-1].content)
                else:
                    print("...")

            # 确认当前成果
            elif command == "ok":
                # 尝试更新当前游标指向的内容
                # 如果更新失败，就要退出循环
                if self.focus == "END":
                    continue
                else:
                    self.todo_content.ok(self.ai_reply_json) 

                # 获取下一个任务的计划
                self.move_focus_auto()
                self.print_todos()
                if self.focus == "START":
                    pass
                elif self.focus == "END":
                    # 全部结束，打印成果出来瞧瞧
                    self.print_text()
                    if self.auto == "all":
                        break
                    else:
                        self.auto = "askme"
                else:
                    # 如果下一个任务存在，继续转移到新的扩写任务
                    prompt = self.user_said_continue()

                    # 如果不移动任务游标，就一直使用这个chain
                    chain = self.update_chain(llm)

                self.ask_ai(chain, prompt)

            # 查看所有任务
            elif command == "children":
                self.process_content_command(focus, id, 'children', None)

            # 查看或修改字数建议
            elif command == "words":
                if prompt and prompt.isdigit():
                    prompt = int(prompt)
                self.process_content_command(focus, id, "words_advice", prompt)

                # 修改当前目标属性，所以要重新生成LLM链
                if focus == self.focus:
                    chain = self.update_chain(llm)

            # 查看或修改标题
            elif command == "title":
                self.process_content_command(focus, id, "title", prompt)

                # 修改当前目标属性，所以要重新生成LLM链
                if focus == self.focus:
                    chain = self.update_chain(llm)

            # 查看或修改扩写指南
            elif command == "howto":
                self.process_content_command(focus, id, "howto", prompt)

                # 修改当前目标属性，所以要重新生成LLM链
                if focus == self.focus:
                    chain = self.update_chain(llm)

            # 查看或修改内容摘要
            elif command == "summarise":
                self.process_content_command(focus, id, "summarise", prompt)

                # 修改当前目标属性，所以要重新生成LLM链
                if focus == self.focus:
                    chain = self.update_chain(llm)

            # 重新加载
            # 在更新提示语模板、变量之后
            elif command == "reload":
                print("已经更新访问AI的参数配置")
                chain = self.update_chain(llm)
            
            # 查看记忆
            elif command == "memory":
                print(self.get_memory(focus))

            # 查看记忆
            elif command == "store":
                print(self.memory._shorterm_memory_store)

            # 其他命令暂时没有特别处理
            else:
                print("UNKOWN COMMAND:", command)

