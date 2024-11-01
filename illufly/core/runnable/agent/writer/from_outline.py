from typing import List, Union

from .....utils import raise_invalid_params, minify_text
from .....io import EventBlock
from ....document import Document
from ...prompt_template import PromptTemplate
from ..base import BaseAgent
from ..chat import ChatAgent
from ..flow import FlowAgent
from .markdown import Markdown

import copy
import asyncio

class FromOutline(BaseAgent):
    """
    实现扩写：从输出结果提炼大纲，然后生成内容。
    """
    @classmethod
    def allowed_params(cls):
        return {
            "writer": "扩写智能体",
            "prev_k": "前 k 个字符",
            "next_k": "后 k 个字符"
        }

    def __init__(self, writer: Union[ChatAgent, FlowAgent]=None, template_id: str=None, prev_k:int=1000, next_k:int=500, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        if not isinstance(writer, (ChatAgent, FlowAgent)):
            raise ValueError("扩写智能体 writer 必须是 ChatAgent 或 FlowAgent 实例")

        super().__init__(**kwargs)
        self.writer = writer
        self.template_id = template_id or "WRITER/FromOutline"

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
                md.replace_documents(doc_id, doc_id, [Document(from_outline_text + "\n")])
            return md.text
        else:
            return self.outline_text

    def fetch_outline(self):
        """
        提取大纲。
        """
        self.markdown = Markdown(self.outline_text)
        return self.markdown.get_outline() if self.markdown else []

    def call(self, outline: Union[str, BaseAgent], *args, **kwargs):
        """
        执行扩写。
        """

        if isinstance(outline, str):
            self.outline_text = outline
        elif isinstance(outline, BaseAgent):
            self.outline_text = outline.last_output
        else:
            raise ValueError("outline 必须是字符串或 BaseAgent 实例")

        # 提取大纲
        outline_docs = self.fetch_outline()

        if outline_docs:
            for doc in outline_docs:
                outline_id = doc.meta['id']
                (draft, outline) = self.markdown.fetch_outline_task(doc, prev_k=self.prev_k, next_k=self.next_k)

                info = f"执行扩写任务 <{outline_id}>：\n{minify_text(outline)}"
                yield EventBlock("agent", info)

                # print("*" * 100)
                # print(draft)
                if isinstance(self.writer, FlowAgent):
                    input_text = PromptTemplate(self.template_id).format({
                        "outline": lambda: f'```markdown\n{outline}\n```',
                        "draft": lambda: f'```markdown\n{draft}\n```'
                    })
                    yield from self.writer.call(input_text)

                elif isinstance(self.writer, ChatAgent):
                    yield from self.writer.call([
                        (
                            'system',
                            PromptTemplate(
                                self.template_id,
                                binding_map={
                                    "outline": lambda: f'```markdown\n{outline}\n```',
                                    "draft": lambda: f'```markdown\n{draft}\n```'
                                }).format()
                        ),
                        (
                            'user',
                            "请开始扩写"
                        )
                    ])
                else:
                    raise ValueError("writer 必须是 ChatAgent 或 FlowAgent 实例")

                self.segments.append(
                    (
                        self.writer.thread_id,
                        outline_id,
                        self.writer.last_output
                    )
                )

        else:
            yield EventBlock("info", f"没有提纲可供扩写")

    async def async_call(self, outline: Union[str, BaseAgent], *args, **kwargs):
        """
        执行扩写。

        注意，该异步版本使用使用 asyncio.gather 并行处理异步生成器时，
        所有的结果会在所有任务完成后一次性返回。
        这是因为 asyncio.gather 会等待所有协程完成，然后返回结果。 
        """

        if isinstance(outline, str):
            self.outline_text = outline
        elif isinstance(outline, BaseAgent):
            self.outline_text = outline.last_output
        else:
            raise ValueError("outline 必须是字符串或 BaseAgent 实例")

        # 提取大纲
        outline_docs = self.fetch_outline()

        async def process_doc(doc):
            outline_id = doc.meta['id']
            (draft, outline) = self.markdown.fetch_outline_task(doc, prev_k=self.prev_k, next_k=self.next_k)

            info = f"执行扩写任务 <{outline_id}>：\n{minify_text(outline)}"
            yield EventBlock("agent", info)

            if isinstance(self.writer, FlowAgent):
                input_text = PromptTemplate(self.template_id).format({
                    "outline": lambda: f'```markdown\n{outline}\n```',
                    "draft": lambda: f'```markdown\n{draft}\n```'
                })
                async for block in self.writer.async_call(input_text):
                    yield block

            elif isinstance(self.writer, ChatAgent):
                async for block in self.writer.async_call([
                    (
                        'system',
                        PromptTemplate(
                            self.template_id,
                            binding_map={
                                "outline": lambda: f'```markdown\n{outline}\n```',
                                "draft": lambda: f'```markdown\n{draft}\n```'
                            }).format()
                    ),
                    (
                        'user',
                        "请开始扩写"
                    )
                ]):
                    yield block

            # 确保在处理完所有块后再更新 segments
            self.segments.append(
                (
                    self.writer.thread_id,
                    outline_id,
                    self.writer.last_output
                )
            )

        async def gather_docs():
            if outline_docs:
                tasks = [process_doc(doc) for doc in outline_docs]
                results = await asyncio.gather(*[self._consume_async_gen(process_doc(doc)) for doc in outline_docs])
                for result in results:
                    for block in result:
                        yield block
            else:
                yield EventBlock("info", f"没有提纲可供扩写")

        async for block in gather_docs():
            yield block

    async def _consume_async_gen(self, agen):
        """
        Helper function to consume an async generator and return a list of results.
        """
        results = []
        async for item in agen:
            results.append(item)
        return results

