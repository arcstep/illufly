from typing import List, Union, Optional
from ..base import Runnable

class Retriever(Runnable):
    """
    检索器。

    实现流程包括：意图理解 -> 初步查询 -> 整理结果

    其中，意图理解包括：
    - 原问题检索
    - 拆解检索
    - 发散检索
    - 回溯检索
    - 模拟回答检索

    初步查询主要通过 ToolAgent 或 VectorDB 实现，通常包括：
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
        self.translators = translators or []
        self.searchers = searchers or []
        self.reranker = reranker
        self.top_k = top_k

    def call(self, query: str) -> List[dict]:
        """
        检索过程的具体实现包括如下过程：
        1. 意图理解：如果提供 translators，则分别转换问题，并合并为问题列表
        2. 初步查询：如果提供 searchers，则使用 searchers 分别查询问题列表
        3. 整理结果：如果提供 reranker，则使用 reranker 重新排序结果
        """
        understood_queries = self.understand(query)
        results_list = self.query(understood_queries)
        organized_results = self.organize(results_list)
        return organized_results

    def understand(self, query: str) -> List[str]:
        results = []
        for translator in self.translators:
            translated_query = translator.run(query)
            if isinstance(translated_query, str):
                results.append(translated_query)
            elif isinstance(translated_query, list):
                results.extend(translated_query)
            else:
                raise ValueError("Unknown translation result type")
        return results

    def query(self, queries: List[str]) -> List[dict]:
        results = []
        for query in queries:
            for searcher in self.searchers:
                results.extend(searcher(query))
        return results

    def organize(self, results_list: List[dict]) -> List[dict]:
        if self.reranker:
            results_list = self.reranker(results_list)
        return results_list

