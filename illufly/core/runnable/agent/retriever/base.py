from typing import List, Union, Optional
from .....utils import extract_segments
from ....document import Document
from ...base import Runnable
from ...vectordb import VectorDB
from ...template import Template
from ...markmeta import MarkMeta
from ..base import BaseAgent

class Retriever(BaseAgent):
    """
    检索器。

    实现流程包括：意图理解 -> 初步查询 -> 整理结果

    初步查询主要通过 工具或 VectorDB 实现，通常包括：
    - 关系型数据库查询
    - 图数据库查询
    - 向量数据库查询

    整理结果主要取决于上一步数据查询的结果，包括：
    - 如果没有排序，就重新排序
    - 如果有排序，且来源于多个结果，就合并排序
    """
    def __init__(
        self,
        translators: List[Runnable]=None,
        searchers: List[Runnable]=None,
        reranker: Runnable=None,
        top_k: int=1,
        **kwargs
    ):
        super().__init__(**kwargs)
        if translators and not isinstance(translators, list):
            translators = [translators]
        if searchers and not isinstance(searchers, list):
            searchers = [searchers]
        self.translators = translators or {}
        self.searchers = searchers or {}
        self.reranker = reranker
        self.top_k = top_k

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
        print("*"*20, "understood_queries", "*"*20, "\n", understood_queries)
        search_results = self.search(understood_queries, **kwargs)
        print("*"*20, "search_results", "*"*20, "\n", search_results)
        rerank_results = self.rerank(query, search_results, **kwargs)
        print("*"*20, "nrerank_results", "*"*20, "\n", rerank_results)
        return rerank_results

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
                if not translator.init_messages:
                    new_messages = [
                        ('system', Template("RAG/QINDEX", binding_map={"count": 3})),
                        ('user', query),
                    ]
                else:
                    new_messages = [
                        ('user', query)
                    ]
                output_text = translator(new_messages, new_chat=True, **kwargs)
                valid_text = extract_segments(output_text, "```", "```", mode="first-last")
                mm = MarkMeta()
                docs = mm.load_text("\n".join(valid_text))
                # mm.save()
                for doc in docs:
                    translated_queries.add(doc.text)

            elif isinstance(translator, VectorDB):
                translated_results = translator(query, **kwargs)
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

    def search(self, queries: List[str]) -> List[dict]:
        """
        初步查询。
        """
        results = set()
        for query in queries:
            for searcher in self.searchers:
                results.update(searcher(query))
        return results

    def rerank(self, query: str, results_list: List[dict]) -> List[dict]:
        """
        整理结果。
        """
        if self.reranker:
            results_list = self.reranker(results_list)
        return results_list

