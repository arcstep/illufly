from typing import List, Union, Optional
from .....config import get_env
from .....utils import extract_segments, minify_text
from .....io import EventBlock
from ....document import Document
from ...base import Runnable
from ...vectordb import VectorDB
from ...prompt_template import PromptTemplate
from ...markmeta import MarkMeta
from ..base import BaseAgent

class Retriever(BaseAgent):
    """
    检索器。

    实现流程包括：意图理解 -> 数据查询 -> 整理结果

    意图理解主要是根据问题索引向量库，或对话模型，将原始问题发散，生成更多提问角度；
    数据查询主要通过 关系数据库、向量数据库、图数据库等实现。

    控制参数说明：
    - 决定广度 question_count: int=3,
    - 决定深度 search_count: int=20,
    - 决定句法关联度 rerank_count: int=5,
    """
    def __init__(
        self,
        translators: List[Runnable]=None,
        searchers: List[Runnable]=None,
        reranker: Runnable=None,
        question_count: int=3,
        search_count: int=20,
        rerank_count: int=5,
        **kwargs
    ):
        if translators and not isinstance(translators, list):
            translators = [translators]
        if searchers and not isinstance(searchers, list):
            searchers = [searchers]

        self.translators = translators or []
        self.searchers = searchers or []
        self.reranker = reranker

        self.question_count = question_count
        self.search_count = search_count
        self.rerank_count = rerank_count

        super().__init__(**kwargs)

        for item in self.translators:
            from ..chat import ChatAgent
            if isinstance(item, ChatAgent) and not item.init_memory:
                item.reset_init_memory(
                    PromptTemplate(
                        "RAG/Q_GEN",
                        binding_map={"count": self.question_count}
                    )
                )
            elif isinstance(item, VectorDB):
                if not item.top_k:
                    item.top_k = question_count
                if not item.documents:
                    item.load(dir=get_env("ILLUFLY_IDENT"))

        for item in self.searchers:
            if isinstance(item, VectorDB):
                if not item.top_k:
                    item.top_k = search_count
                if not item.documents:
                    item.load(dir=get_env("ILLUFLY_DOCS"))

    def call(self, query: str, **kwargs) -> List[dict]:
        """
        检索过程的具体实现包括如下过程：
        1. 意图理解：如果提供 translators，则分别转换问题，并合并为问题列表
        2. 初步查询：如果提供 searchers，则使用 searchers 分别查询问题列表
        3. 整理结果：如果提供 reranker，则使用 reranker 重新排序结果
        """
        understood_queries = set()
        understood_queries.add(query)
        understood_queries.update(self.translate(query, **kwargs))
        yield from self.search(understood_queries, **kwargs)

    def translate(self, query: str, **kwargs) -> List[str]:
        """
        意图理解，将问题翻译为进一步检索的问题列表。
        这个过程可以是：拆解问题、发散问题、回溯问题、模拟回答等，具体取决于 translator 的类型和执行情况。
        translator 可以是 ChatAgent, VectorDB 或 BaseAgent,
        而返回结果可以是 字符串列表、JSON 文本、MarkMeta 文本或 Document 列表等几种格式。
        """
        from ..chat.base import ChatAgent

        translated_queries = set()
        for translator in self.translators:
            if isinstance(translator, ChatAgent):
                output_text = translator(query, new_chat=True)
                valid_text = extract_segments(output_text, "```", "```", mode="first-last")
                mm = MarkMeta()
                docs = mm.load_text("\n".join(valid_text))
                # mm.save()
                for doc in docs:
                    translated_queries.add(doc.text)

            elif isinstance(translator, VectorDB):
                top_k = self.question_count
                translated_results = translator(query)
                for result in translated_results:
                    if isinstance(result, str):
                        translated_queries.add(result)
                    elif isinstance(result, Document):
                        translated_queries.add(result.text)
                    else:
                        raise ValueError("Unknown translation result type")

            else:
                raise ValueError("Unknown translator type")

        return translated_queries

    def search(self, queries: List[str], **kwargs) -> List[dict]:
        """
        初步查询。
        """
        results = set()
        top_k = self.search_count
        for query in queries:
            for searcher in self.searchers:
                yield EventBlock("agent", f"由 {searcher.name} 检索问题：{query}")

                search_results = searcher(query, top_k=top_k, **kwargs)
                for result in search_results:
                    if isinstance(result, str):
                        yield EventBlock("info", f"检索结果[-]：{result}")
                    elif isinstance(result, Document):
                        yield EventBlock("info", f"检索结果[{result.meta['distance']}]：{minify_text(result.text, 30)}")
                    else:
                        raise ValueError("Unknown search result type")

                if search_results:
                    if self.reranker:
                        yield EventBlock("agent", f"由 {self.reranker.name} 重新排序检索结果")
                        rerank_results = self.reranker(query, search_results, top_k=self.rerank_count, **kwargs)
                        for doc in rerank_results:
                            if isinstance(doc, Document):
                                yield EventBlock("info", f"重新排序结果[{doc.meta['rerank_score']}]：{minify_text(doc.text)}")
                            else:
                                raise ValueError("Unknown rerank result type")
                    else:
                        rerank_results = search_results[:self.rerank_count]

                    for doc in rerank_results:
                        if isinstance(doc, Document):
                            results.add(doc)
                        elif isinstance(doc, str):
                            results.add(Document(doc))
                        else:
                            raise ValueError("Unknown search result type")
        self._last_output = results
