from typing import List, Union

from .....utils import raise_invalid_params
from .....io import EventBlock
from .markdown import Markdown
from ..base import BaseAgent
from ..chat import ChatAgent
from ...prompt_template import PromptTemplate

import copy

class FromOutline(BaseAgent):
    """
    实现扩写：从输出结果提炼大纲，然后生成内容。
    """
    @classmethod
    def available_init_params(cls):
        return {
            "writer": "扩写智能体",
            "prev_k": "前 k 个字符",
            "next_k": "后 k 个字符"
        }

    def __init__(self, writer: ChatAgent=None, prev_k:int=1000, next_k:int=500, **kwargs):
        raise_invalid_params(kwargs, self.__class__.available_init_params())

        if not isinstance(writer, ChatAgent):
            raise ValueError("扩写智能体 writer 必须是 ChatAgent 实例")

        super().__init__(**kwargs)
        self.writer = writer

        self.prev_k = prev_k
        self.next_k = next_k

        # 执行 call 调用时提供
        self.outline_text = None
        self.markdown = None

        # 执行 call 调用时生成
        self.segments = []

    @property
    def last_output(self):
        """
        从 Markdown 生成当前的文本输出内容。
        如果当前有提纲，则将提纲中的内容替换为实际内容。
        """
        if self.segments:
            md = copy.deepcopy(self.markdown)
            for (thread_id, doc_id, from_outline_text) in self.segments:
                md.replace_documents(doc_id, doc_id, from_outline_text)
            return md.text
        else:
            return self.outline_text

    def fetch_outline(self, outline_text: str):
        """
        提取大纲。
        """
        self.outline_text = outline_text
        self.markdown = Markdown(self.outline_text)
        return self.markdown.get_outline() if self.markdown else []

    def call(self, outline_text: str, *args, **kwargs):
        """
        执行扩写。
        """

        if not isinstance(outline_text, str):
            raise ValueError("outline_text 必须是字符串")

        # 提取大纲
        outline_docs = self.fetch_outline(outline_text)

        if outline_docs:
            for doc in outline_docs:
                outline_id = doc.meta['id']

                (draft, outline) = self.markdown.fetch_outline_task(doc, prev_k=self.prev_k, next_k=self.next_k)
                self.writer.reset_init_memory(
                    PromptTemplate(
                        "FROM_OUTLINE",
                        binding_map={
                            "outline": f'```markdown\n{outline}\n```',
                            "draft": f'```markdown\n{draft}\n```'
                        }
                    )
                )

                info = f"执行扩写任务 <{outline_id}>：\n{outline}"
                yield EventBlock("agent", info)

                self.writer.clear()
                yield from self.writer.call("请开始扩写")
                self.segments.append((self.writer.thread_id, outline_id, self.writer.last_output))

        else:
            yield EventBlock("info", f"没有提纲可供扩写")

