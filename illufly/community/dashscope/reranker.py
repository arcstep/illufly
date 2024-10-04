from typing import List, Union
from ...core.runnable.reranker.base import BaseReranker
from ...core.document import Document, convert_to_documents_list
from ...config import get_env
from ...io import EventBlock, NewLineBlock

import os
import json
from http import HTTPStatus


class DashScopeReranker(BaseReranker):
    def __init__(self, model: str=None, api_key: str=None, **kwargs):
        try:
            import dashscope
            self.dashscope = dashscope
        except ImportError:
            raise RuntimeError(
                "Could not import dashscope package. "
                "Please install it via 'pip install -U dashscope'"
            )

        super().__init__(
            model=model or "gte-rerank",
            api_key=api_key or os.getenv("DASHSCOPE_API_KEY"),
            **kwargs
        )

    def rerank(self, query: str, docs: Union[str, List[str], List[Document]]):
        """
        重排序器。

        rerank 返回的文档长度应当与 docs 一致，因此 top_n 应当取值为 docs 的长度。
        """
        self._last_output = []
        docs = convert_to_documents_list(docs)
        top_n = len(docs)

        self.dashscope.api_key = self.api_key

        resp = self.dashscope.TextReRank.call(
            model=self.model,
            query=query,
            documents=[doc.text for doc in docs],
            top_n=top_n,
            return_documents=False
        )

        request_id = None
        usage = {}
        final_docs = []
        if resp.status_code == HTTPStatus.OK:
            request_id = resp.request_id
            if "usage" in resp:
                usage = resp.usage
            if "output" in resp:
                output = resp.output
                if "results" in output:
                    results = output["results"]
                    results.sort(key=lambda x: x["index"], reverse=False)
                    for index, result in enumerate(results):
                        doc = docs[index]
                        doc.meta["rerank_score"] = result["relevance_score"]
                        final_docs.append(doc)
                    final_docs.sort(key=lambda x: x.meta["rerank_score"], reverse=True)
                    self._last_output = final_docs

        else:
            yield EventBlock("warn", ('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
                resp.request_id, resp.status_code,
                resp.code, resp.message
            )))

        yield NewLineBlock()
        yield EventBlock(
            "usage",
            json.dumps(usage, ensure_ascii=False),
            calling_info={
                "request_id": request_id,
                "input": {"model": self.model, "query": query, "documents": docs},
                "output": json.dumps(output, ensure_ascii=False),
            }
        )
