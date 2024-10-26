from typing import List, Union, Optional
from ..base import Runnable
from ....core.document import Document, convert_to_documents_list
from ....utils import hash_text, clean_filename, raise_invalid_params
from ....config import get_env
from ....io import EventBlock

import os
import pickle

class BaseReranker(Runnable):
    """
    重排序器。
    ```
    """
    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            "base_url": "API 基础 URL",
            "api_key": "API 密钥",
            "top_k": "返回结果的条数，默认 5",
            **Runnable.allowed_params()
        }

    def __init__(self, model: str=None, base_url: str=None, api_key: str=None, top_k: int=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        super().__init__(**kwargs)
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.top_k = top_k or 5
        self.clear_output()

    def clear_output(self):
        self._last_output = []

    def rerank(self, query: str, docs: Union[str, List[str], List[Document]], **kwargs):
        """
        重排序器。
        """
        return docs

    def call(
        self,
        query: str,
        docs: Union[str, List[str], List[Document]],
        **kwargs
    ) -> List[Document]:
        return self.rerank(query, docs)
