from typing import Any, Dict, Iterator, List, Optional, Union
from langchain_core.runnables import Runnable
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from langchain.memory import ConversationBufferMemory, ConversationBufferWindowMemory
from ..memory.history import LocalFileMessageHistory, create_session_id
from ..memory.memory_manager import MemoryManager
from ..memory.base import WithMemoryBinding
from .serialize import ContentSerialize
from .state import ContentState
from .command import BaseCommand
import datetime
import random

_INVALID_PROMPT_INPUT = ["title", "words_advice", "howto", "summarise", "text"]

def generate_sn(numbers: List[int]) -> str:
    return ".".join(str(number) for number in numbers)

class ContentNode(ContentState, ContentSerialize, BaseCommand):
    """
    存储内容的树形结构，段落内容保存在叶子节点，而提纲保存在children的列表中。    
    """

    def __init__(
        self,
        type: str = None,
        words_limit_per_paragraph: int = 500,
        words_advice: int = None,
        title: str = None,
        howto: str = None,
        summarise: str = None,
        text: str = None,
    ):
        ContentState.__init__(self)
        ContentSerialize.__init__(self)

        self.type = type

        # 如果超出这个段落字数就拆分为提纲
        self.words_limit_per_paragraph = words_limit_per_paragraph

        # 扩写指南
        self.words_advice = words_advice
        self.title = title
        self.howto = howto

        # 段落
        self.summarise = summarise
        self.text = text

        # 最后的AI回复
        self.last_ai_reply_json: Dict[str, str] = {}

    # inherit
    @staticmethod
    def commands(self) -> List[str]:
        return [
            "title", "howto", "text", "words_advice", "children", 
            "ok", "todo", "modi", "state", "is_complete",
        ]

    # inherit
    def call(self, command: str = None, args: str = None, **kwargs):
        if command == "ok":
            res = self.ok()
        elif command == "ok":
            res = self.ok()
        elif command == "state":
            res = self.state
        else:
            res = self._cmd_process_content_command(command, args)

        return res

    # 设置提示语输入
    def _cmd_set_prompt_input(self, k: str, v: str):
        """
        修改创作依据将引起状态变化。
        """
        if k in _INVALID_PROMPT_INPUT and v != None:
            if self.state == "done":
                self._fsm.done_mod()
            return setattr(self, k, v)
        else:
            raise BaseException("No prompt input KEY: ", k)

    def _cmd_get_prompt_input(self, k: str):
        if k in _INVALID_PROMPT_INPUT:
            return getattr(self, k)
        else:
            raise BaseException("No prompt input KEY: ", k)

    def _cmd_process_content_command(self, k, v):
        if k in ['words_advice', 'title', 'howto', 'summarise', 'text']:
            # 设置内容属性
            if v != None:
                self._cmd_set_prompt_input(k, v)

            # 打印指定对象的指定属性
            print(f'{k:}', self._cmd_get_prompt_input(k))
        else:
            raise BaseException("Invalid Node Key: ", k)
    
    def reply_json_validator(self, item:Dict[str, Any], keys:List[str]):
        for k in keys:
            if k not in item:
                raise(BaseException(f"缺少必要的字段：{item}"))

    def on_init_todo(self):
        super().on_init_todo()

        self.reply_json_validator(self.last_ai_reply_json, ["标题名称", "总字数要求", "扩写指南"])

        self.title = self.last_ai_reply_json["标题名称"]
        self.howto = self.last_ai_reply_json["扩写指南"]
        self.words_advice = self.last_ai_reply_json["总字数要求"]
        self.type = "outline" if self.words_advice > self.words_limit_per_paragraph else "paragraph"

    def on_todo_done(self):
        super().on_todo_done()

        if self.type == "outline":
            # 删除旧的子项，逐个添加新的子项
            self.children = {}
            self.reply_json_validator(self.last_ai_reply_json, ["大纲列表"])

            for item in self.last_ai_reply_json['大纲列表']:
                self.reply_json_validator(item, ["标题名称", "总字数要求", "扩写指南"])

                self.add_item(
                    title = item['标题名称'],
                    howto = item['扩写指南'],
                    words_advice = item['总字数要求'],
                )

        elif self.type == "paragraph":
            self.reply_json_validator(self.last_ai_reply_json, ["内容摘要", "详细内容"])
            self.summarise = self.last_ai_reply_json["内容摘要"]
            self.text = self.last_ai_reply_json["详细内容"]
        
        else:
            raise BaseException("Invalid type for content: ", self.type)

