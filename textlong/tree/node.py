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

    def __init__(
        self,
        ## self
        type: str="unknown",
        words_limit: int=500,
        words_advice: int=None,
        title: str=None,
        howto: str=None,
        ## AI
        last_ai_reply_json: Dict[str, Any]={},
        is_draft: bool=False,
        llm=None,
        memory=None,
        ## ContentState
        state=None,
        ## 段落
        summarise: str=None,
        text: str=None,
        ## prompt
        help_prompt=None,
        init_prompt=None,
        outline_prompt=None,
        paragraph_prompt=None,
        ## project_id, index, parent 等
        **kwargs,
    ):

        BaseCommand.__init__(self)
        ContentSerialize.__init__(self, **kwargs)
        if state:
            ContentState.__init__(self, start_value=state)
        else:
            ContentState.__init__(self)

        # self
        self.type = type
        self.words_limit = words_limit
        self.words_advice = words_advice
        self.title = title
        self.howto = howto

        # 段落
        self.summarise = summarise
        self.text = text
        
        # prompt
        self.help_prompt = help_prompt
        self.init_prompt = init_prompt
        self.outline_prompt = outline_prompt
        self.paragraph_prompt = paragraph_prompt

        # 最后的AI回复
        self.last_ai_reply_json = last_ai_reply_json
        self.is_draft = is_draft
        self.ai = BaseAI(llm, memory)

    # 指令清单
    howto_commands = ["title", "words_advice", "howto"]
    result_commands = ["summarise", "text"]
    state_commands = ["state", "memory", "ok", "todo", "modi", "task"]

    # inherit
    @property
    def commands(self) -> List[str]:
        """
        TODO: 考虑动态返回可用的指令集。
              但要避免不合法的指令被当作默认指令的参数返回！！！
        """
        return self.howto_commands + self.result_commands + self.state_commands + [self.default_command]

    # inherit
    def call(self, command: str=None, args: str=None, **kwargs):
        if command == "state":
            return {"id": self.id, "state": self.state, "is_draft": self.is_draft, "is_complete": self.is_complete}
        elif command == "memory":
            return self.ai.memory.buffer_as_str
        elif command == "ok":
            if self.state == "todo" and not self.is_draft:
                return self.ask_ai(task="请继续。")
            else:
                if self.state in ['init', 'todo']:
                    self.ok()
                return self.state
        elif command == "help":
            return self.help_ai(task=args)
        elif command == "task":
            if self.state == "done":
                return "<END>"
            else:
                return self.ask_ai(task=args)
        elif command in self.result_commands:
            res = self._cmd_set_prop(command, args) if args and len(args) > 0 else self._cmd_get_prop(command)
            return res
        elif command in self.howto_commands:
            if args and len(args) > 0:
                # 修改扩写依据后，应当取消草稿状态：
                #   以便优先触发task指令，重新生成结果
                res = self._cmd_set_prop(command, args)
                self.is_draft = False
            else:
                # 打印指定对象的指定属性
                res = self._cmd_get_prop(command)
            return res

        raise NotImplementedError(f"尚未实现这个命令：{command}")

    # inherit
    @property
    def default_command(self) -> str:
        return "help"

    def help_ai(self, task: str=None):
        """向AI询问，获得生成结果"""

        default_task = "有哪些命令可以使用？"

        prompt = self.help_prompt
        chat = self.ai.ask_ai(task or default_task, prompt, return_json=False)

        return chat

    def ask_ai(self, task: str=None):
        """向AI询问，获得生成结果"""

        default_task = "请开始。"

        if self.state == "init":
            prompt = self.init_prompt

        elif self.state == "todo" and self.type == "outline":
            prompt = self.outline_prompt.partial(
                title=self.title,
                content_type=self.type,
                words_limit=self.words_limit,
                words_advice=self.words_advice,
                howto=self.howto,
                outline_exist=self.root.get_outlines()
            )
        elif self.state == "todo" and self.type == "paragraph":
            prompt = self.paragraph_prompt.partial(
                title=self.title,
                content_type=self.type,
                words_limit=self.words_limit,
                words_advice=self.words_advice,
                howto=self.howto,
                outline_exist=self.root.get_outlines()
            )
        else:
            raise NotImplementedError(f"<{self.id}> 对象在状态[{self.state}]没有指定提示语模板")

        json = self.ai.ask_ai(task or default_task, prompt, return_json=True)
        self.last_ai_reply_json = json
        self.is_draft = True

        return json

    # 设置提示语输入
    def _cmd_set_prop(self, k: str, v: str):
        setattr(self, k, v)
        if self.state != 'todo':
            self.edit()
        return True

    def _cmd_get_prop(self, k: str):
        return getattr(self, k)

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
                    words_advice = item["总字数要求"]
                    type = "outline" if words_advice > self.words_limit else "paragraph"
                    title = item["标题名称"]
                    howto = item["扩写指南"]
                    node = self.add_item(
                        type=type,
                        title=title,
                        howto=howto,
                        words_advice=words_advice,
                        last_ai_reply_json=item,
                        is_draft=False,
                        item_class=ContentNode,

                        ## 以下这些属性将会继承父节点的配置
                        help_prompt=self.help_prompt,
                        init_prompt=self.init_prompt,
                        outline_prompt=self.outline_prompt,
                        paragraph_prompt=self.paragraph_prompt,
                        llm=self.ai.llm,
                        memory=self.ai.memory,
                    )
                    node.edit()

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
            "words_limit": self.words_limit,
            "words_advice": self.words_advice,
            "title": self.title or "",
            "howto": self.howto or "",
            "summarise": self.summarise or "",
            "text": self.text or "",
            "last_ai_reply_json": self.last_ai_reply_json,
        }

    def get_outlines(self) -> List[Dict[str, Union[str, int]]]:
        """获得大纲清单"""
        outlines = [
            f"{x['id']} {x['title']} \n  扩写指南 >>> {x['howto']}\n  内容摘要 >>> {x['summarise']}"
            for x in self.all_content
        ]
        return '\n'.join(outlines)

    def get_texts(self):
        outlines = [
            f"{x['id']} {x['title']} \n {x['text']}"
            for x in self.all_content
        ]
        return '\n'.join(outlines)
