from typing import List, Union, Optional
from ..base import BaseAgent
from ...vectordb import VectorDB
from ...base import Runnable

class Retriever(BaseAgent):
    """
    检索器。

    实现流程包括：意图理解 -> 初步查询 -> 整理结果


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
        if translators and not isinstance(translators, list):
            translators = [translators]
        if searchers and not isinstance(searchers, list):
            searchers = [searchers]
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
        understood_queries = self.translate(query)
        results_list = self.search(understood_queries)
        organized_results = self.rerank(results_list)
        return organized_results

    def translate(self, query: str, **kwargs) -> List[str]:
        """
        意图理解，将问题翻译为进一步检索的问题列表。
        这个过程可以是：拆解问题、发散问题、回溯问题、模拟回答等，具体取决于 translator 的类型和执行情况。
        translator 可以是 ChatAgent, VectorDB 或 ToolAgent,
        而返回结果可以是 字符串列表、JSON 文本、MarkMeta 文本或 Document 列表等几种格式。
        """
        results = []
        translated_queries = []
        for translator in self.translators:
            results = translator(query, **kwargs)
            if isinstance(results, str):
                start = None
                end = None
                if results.find("```json") != -1:
                    start = results.find("```json\n")
                    end = results.find("\n```", start + 1)
                    results = json.loads(results[start:end])
                elif results.find("```") != -1:
                    results = markdown(results)
                translated_queries.append(results)
            elif isinstance(results, list):
                for result in results:
                    if isinstance(result, str):
                        translated_queries.append(result)
                    elif isinstance(result, Document):
                        translated_queries.append(result.text)
                    else:
                        raise ValueError("Unknown translation result type")
            else:
                raise ValueError("Unknown translation result type")
            if isinstance(translator, VectorDB):
                translated_query = translator.run(query)
            elif isinstance(translator, Callable):
                translated_query = translator(query)
            else:
                raise ValueError("Unknown translator type")
            if isinstance(translated_query, str):
                results.append(translated_query)
            elif isinstance(translated_query, list):
                results.extend(translated_query)
            else:
                raise ValueError("Unknown translation result type")
        return results

    def search(self, queries: List[str]) -> List[dict]:
        """
        初步查询。
        """
        results = []
        for query in queries:
            for searcher in self.searchers:
                results.extend(searcher(query))
        return results

    def rerank(self, results_list: List[dict]) -> List[dict]:
        """
        整理结果。
        """
        if self.reranker:
            results_list = self.reranker(results_list)
        return results_list

