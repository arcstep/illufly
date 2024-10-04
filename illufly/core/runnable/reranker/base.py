from typing import List, Union, Optional
from ..base import Runnable
from ....core.document import Document, convert_to_documents_list
from ....utils import hash_text, clean_filename
from ....config import get_env
from ....io import EventBlock

import os
import pickle

class BaseReranker(Runnable):
    """
    重排序器。
    ```
    """

    def __init__(self, model: str=None, base_url: str=None, api_key: str=None, dim: int=None, max_lines: int=None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.clear_output()

    def clear_output(self):
        self._last_output = []

    def rerank(self, query: str, docs: Union[str, List[str], List[Document]]):
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
