from typing import List, Union

from ....io import TextBlock
from ....utils import compress_text
from ...parser import Markdown
from ..base import BaseAgent
from ..chat import ChatAgent
from ..team import Pipe

import copy

class FromOutline(BaseAgent):
    """
    实现扩写：从输出结果提炼大纲，然后生成内容。
    """
    def __init__(self, writer: ChatAgent=None, prev_k:int=1000, next_k:int=500):
        if not isinstance(writer, ChatAgent):
            raise ValueError("扩写智能体 writer 必须是 ChatAgent 实例")

        super().__init__("FROM_OUTLINE")
        self.writer = writer
        self.prev_k = prev_k
        self.next_k = next_k

        # 执行 call 调用时提供
        self.outline_text = None

        # 执行 call 调用时生成
        self.markdown = Markdown()
        self.outline = []
        self.runnables = {}

    @property
    def output(self):
        """
        从 Markdown 生成当前的文本输出内容。
        如果当前有提纲，则将提纲中的内容替换为实际内容。
        """
        if self.outline:
            md = copy.deepcopy(self.markdown)
            for doc in self.outline:
                if doc.metadata['id'] in self.runnables:
                    from_outline_text = self.runnables[doc.metadata['id']].memory[-1]['content']
                    md.replace_documents(doc, doc, from_outline_text)
            return md.text
        else:
            return self.outline_text

    def call(self, outline_text: str, *args, **kwargs):
        """
        执行扩写。
        """

        if not isinstance(outline_text, str):
            raise ValueError("outline_text 必须是字符串")

        if self.outline_text != outline_text:
            self.markdown = Markdown(outline_text)
            self.outline = self.markdown.get_outline() if self.markdown else []
            self.outline_text = outline_text

        if self.outline:
            for doc in self.outline:
                outline_id = doc.metadata['id']

                segment_writer = self.writer.clone()
                self.runnables[doc.metadata['id']] = segment_writer

                (draft, outline) = self.markdown.fetch_outline_task(doc, prev_k=self.prev_k, next_k=self.next_k)
                segment_writer.set_outline(f'```markdown\n{outline}\n```')
                segment_writer.set_draft(f'```markdown\n{draft}\n```')

                info = f"执行扩写任务 <{outline_id}>：\n{outline}"
                yield TextBlock("agent", info)
                self.create_new_memory(info)
                for block in segment_writer.call("请开始扩写"):
                    yield block
                self.remember_response(segment_writer.output)
        else:
            yield TextBlock("info", f"没有提纲可供扩写")

