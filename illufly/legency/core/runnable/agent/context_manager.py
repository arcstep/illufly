import os
import shutil
from typing import Any, Set, Union, List

from ....config import get_env
from ....io import Document
from ....community import BaseChat as VectorDB

class ContextManager:
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "context": "待检索的上下文信息",
            "vectordbs": "向量数据库实例集合",
        }

    def __init__(
        self,
        context: Union[Set[Any], List[Any]] = None,
        vectordbs: Union[VectorDB, Set[VectorDB], List[VectorDB]] = None,
    ):
        """
        上下文环境在内存中以集合的方式保存，确保唯一性。
        向量数据库集合用于管理多个向量库实例，支持并行检索。
        """
        # 初始化上下文集合
        if isinstance(context, list):
            self.context = set(context)
        elif not isinstance(context, set):
            self.context = set({context}) if context else set()
        else:
            self.context = context

        # 初始化向量数据库集合
        if isinstance(vectordbs, VectorDB):
            self.vectordbs = {vectordbs}
        elif isinstance(vectordbs, list):
            self.vectordbs = set(vectordbs)
        elif isinstance(vectordbs, set):
            self.vectordbs = vectordbs
        else:
            self.vectordbs = set()

    def add_context(self, item: Union[str, Document]):
        """
        添加上下文信息到环境中。
        """
        if isinstance(item, (str, Document)):
            self.context.add(item)
        else:
            raise ValueError("Context MUST be a string or Document")

    def add_vectordb(self, vectordb: VectorDB):
        """
        添加向量数据库实例到管理集合中。
        """
        if isinstance(vectordb, VectorDB):
            self.vectordbs.add(vectordb)
        else:
            raise ValueError("vectordb MUST be a VectorDB instance")

    def query(self, query: str=None, verbose: bool=False):
        """
        获取上下文信息和所有向量数据库的检索结果。
        """
        contexts = []
        # 处理内存中的上下文
        for ctx in self.context:
            if isinstance(ctx, Document):
                contexts.append(ctx)
            elif isinstance(ctx, str):
                contexts.append(Document(text=ctx, meta={"source": "直接资料"}))
            else:
                raise ValueError("Context MUST be a string or Document")
        
        # 如果有向量数据库且提供了查询，则从所有向量库中检索
        if self.vectordbs and query:
            for vectordb in self.vectordbs:
                docs = vectordb.query(query, verbose=verbose)
                contexts.extend(docs)
            
        return contexts
