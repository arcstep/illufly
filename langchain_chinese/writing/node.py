from typing import Any, Dict, Iterator, List, Optional, Union
from langchain_core.runnables import Runnable
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from .serialize import ContentSerialize
from .state import ContentState
from .command import BaseCommand
from .ai import BaseAI
import datetime
import random

class ContentNode(ContentState, ContentSerialize, BaseCommand):
    """
    树形结构的内容存储节点，段落内容保存在叶子节点，而提纲保存在children的列表中。
    """

    invlalid_prop_commands = ["title", "words_advice", "howto", "summarise", "text"]

    def __init__(
        self,
        type: str="unknown",
        words_limit: int=500,
        words_advice: int=None,
        title: str=None,
        howto: str=None,
        summarise: str=None,
        text: str=None,
        last_ai_reply_json: Dict[str, Any]={},
        **kwargs,
    ):
        ContentState.__init__(self)
        ContentSerialize.__init__(self, **kwargs)

        self.type = type

        # 如果超出这个段落字数就拆分为提纲
        self.words_limit = words_limit

        # 扩写指南
        self.words_advice = words_advice
        self.title = title
        self.howto = howto

        # 段落
        self.summarise = summarise
        self.text = text

        # 最后的AI回复
        self.last_ai_reply_json = last_ai_reply_json

        self.is_draft: bool = False
        self.ai = BaseAI()

    # inherit
    @property
    def commands(self) -> List[str]:
        """动态返回可用的指令集"""
        if self.state == "init":
            if self.last_ai_reply_json is None:
                return ["task"]
            elif self.howto is None:
                return ["task", "ok"]
            else:
                return self.invlalid_prop_commands + ["task", "ok"]
        elif self.state in ["todo", "modi"]:
            return self.invlalid_prop_commands + ["task", "ok"]
        else:
            return self.invlalid_prop_commands

    # inherit
    def call(self, command: str=None, args: str=None, **kwargs):
        if command == "task":
            return self.ask_ai(task=args)
        elif command == "ok":
            self.ok()
            return self.state
        elif command == "state":
            return self.state
        elif command in self.invlalid_prop_commands:
            if v != None:
                # 设置内容属性
                res = self._cmd_set_prop(k, v)
            else:
                # 打印指定对象的指定属性
                res = self._cmd_get_prop(k)
            return res

        raise NotImplementedError(f"尚未实现这个命令：{command}")

    # inherit
    @property
    def default_command(self) -> str:
        return "task"

    def ask_ai(self, task: str=None):
        """向AI询问，获得生成结果"""

        task = task or "请开始。"

        if self.state == "init":
            prompt = self.ai.prompt_init()

        elif self.state == "todo":
            prompt = self.ai.prompt_todo(
                title=self.title,
                content_type=self.type,
                words_limit=self.words_limit,
                words_advice=self.words_advice,
                howto=self.howto,
                outline_exist=self.root.all_outlines
            )

        else:
            raise NotImplementedError(f"<{self.id}> 对象在状态[{self.state}]没有指定提示语模板")

        chain = self.ai.get_chain(prompt)
        json = self.ai.ask_ai(task, chain, return_json=True)
        self.last_ai_reply_json = json
        self.is_draft = True
        return json

    # 设置提示语输入
    def _cmd_set_prop(self, k: str, v: str):
        if k in self.invlalid_prop_commands and v != None:
            if self.state == "done":
                # 如果修改属性，则转为修改状态
                self._fsm.done_mod()
            setattr(self, k, v)
            return True
        else:
            raise BaseException("No prompt input KEY: ", k)

    def _cmd_get_prop(self, k: str):
        if k in self.invlalid_prop_commands:
            return getattr(self, k)
        else:
            raise BaseException("No prompt input KEY: ", k)

    def reply_json_validator(self, item:Dict[str, Any], keys:List[str]):
        for k in keys:
            if k not in item:
                raise(BaseException(f"缺少必要的字段：{item}"))

    def on_init_todo(self):
        # super().on_init_todo()

        self.reply_json_validator(self.last_ai_reply_json, ["标题名称", "总字数要求", "扩写指南"])
        self.title = self.last_ai_reply_json["标题名称"]
        self.howto = self.last_ai_reply_json["扩写指南"]
        self.words_advice = self.last_ai_reply_json["总字数要求"]
        self.type = "outline" if self.words_advice > self.words_limit else "paragraph"
        self.is_draft = False

    def on_todo_done(self):
        # super().on_todo_done()

        if self.is_draft:
            if self.type == "outline":
                # 删除旧的子项，逐个添加新的子项
                self._children = {}
                self.reply_json_validator(self.last_ai_reply_json, ["大纲列表"])

                for item in self.last_ai_reply_json['大纲列表']:
                    self.reply_json_validator(item, ["标题名称", "总字数要求", "扩写指南"])
                    self.add_item(
                        item_class=ContentNode,
                        last_ai_reply_json=item,
                        is_draft=True
                    )

            elif self.type == "paragraph":
                self.reply_json_validator(self.last_ai_reply_json, ["内容摘要", "详细内容"])
                self.summarise = self.last_ai_reply_json["内容摘要"]
                self.text = self.last_ai_reply_json["详细内容"]

            else:
                raise BaseException("Unknown type for content: ", self.id)

            self.is_draft = False

    def find_not_complete_node(self, type=None):
        """查询未完成子项"""

        obj = None
        search_types = ["outline", "paragraph", "unknown"] if type == None else [type]

        if not self.is_complete and self.type in search_types:
            return self

        for child in self._children.values():
            if not child.is_complete and child.type in search_types:
                obj = child
            else:
                if child._children:
                    obj = child.find_not_complete_node(type)

            if obj:
                break

        return obj

    def find_draft_node(self, type=None):
        """查询未完成子项"""

        obj = None
        search_types = ["outline", "paragraph", "unknown"] if type == None else [type]

        if self.is_draft and self.type in search_types:
            return self

        for child in self._children.values():
            if child.is_draft and child.type in search_types:
                obj = child
            else:
                if child._children:
                    obj = child.find_draft_node(type)

            if obj:
                break

        return obj

    @property
    def content(self) -> Dict[str, Union[str, int]]:
        return {
            "id": self.id,
            "type": self.type,
            "state": self.state,
            "is_complete": self.is_complete,
            "is_draft": self.is_draft,
            "words_advice": self.words_advice,
            "title": self.title or "",
            "howto": self.howto or "",
            "summarise": self.summarise or None,
            "text": self.text or "",
        }

    @property
    def all_outlines(self) -> List[Dict[str, Union[str, int]]]:
        """获得大纲清单"""
        outlines = [
            f"{x['id']} {x['title']} \n  扩写指南 >>> {x['howto']}\n  内容摘要 >>> {x['summarise']}"
            for x in self.all_content
        ]
        return '\n'.join(outlines)

    @property
    def all_text(self):
        outlines = [
            f"{x['id']} {x['title']} \n {x['text']}"
            for x in self.all_content
        ]
        return '\n'.join(outlines)
