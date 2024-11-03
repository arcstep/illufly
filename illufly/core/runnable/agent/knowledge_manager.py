import os
import shutil
from typing import Any, Set, Union, List

from ....config import get_env
from ...document import Document
from ..vectordb import VectorDB
from ...team import Team
from .retriever import Retriever

class KnowledgeManager:
    @classmethod
    def allowed_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "knowledge": "待检索的资料或向量数据库",
            "team": "所属团队"
        }

    def __init__(
        self,
        knowledge: Union[Set[Any], List[Any]] = None,
        team: Team = None,
    ):
        """
        知识库在内存中以集合的方式保存，确保唯一性。

        默认情况下，会将提供的第一个向量数据库作为默认向量库，默认向量库将自动加载 __ILLUFLY_DOCS__ 和 __ILLUFLY_CHAT_LEARN__ 目录下的文档。
        除非在其他向量库中已经指定了如何加载这两个目录。
        """
        self.knowledge = knowledge

        # 所属团队
        self.team = team

        if isinstance(knowledge, list):
            self.knowledge = set(knowledge)

        if not isinstance(self.knowledge, set):
            self.knowledge = set({self.knowledge}) if self.knowledge else set()

        self.default_docs = set({})
        self.default_vdb = None

        self._recalled_knowledge = []

        self.load_default_knowledge()
        self.load_resource_knowledge()

    @property
    def recalled_knowledge(self):
        """
        返回最近一次调用 get_knowledge 方法时返回的资料列表。
        """
        return self._recalled_knowledge

    def load_default_knowledge(self):
        """
        加载默认知识库。
        """
        self.default_docs = set({
            get_env("ILLUFLY_DOCS"),
            self.team.chat_learn_folder if self.team else get_env("ILLUFLY_CHAT_LEARN")
        })
        for item in self.knowledge:
            if not isinstance(item, (str, Document, VectorDB, Retriever)):
                raise ValueError("Knowledge list items MUST be str, Document or VectorDB")

            if isinstance(item, VectorDB):
                if not self.default_vdb:
                    self.default_vdb = item
                if item in item.sources:
                    # 如果已经在向量库中指定了文档目录，则不再从默认文档目录中加载
                    self.default_docs.remove(item)

        if self.default_vdb:
            for doc_folder in self.default_docs:
                self.default_vdb.load(dir=doc_folder)

    def _get_resource_type(self, ext: str):
        return {
            "jpg": "图片",
            "png": "图片",
            "mp4": "视频",
        }.get(ext, "其他文件")

    def load_resource_knowledge(self, resource_dir: str=None, extensions: List[str]=None):
        """
        自动扫描资源目录中的可观测资源，将其中的图片、视频、音频等可作为资源使用的文件信息提炼为知识，添加到知识库中。
        """
        extensions = extensions or ["jpg", "png", "mp4", "mp3", "wav"]
        resource_docs = resource_dir or get_env("ILLUFLY_RESOURCE")
        if resource_docs:
            if os.path.exists(resource_docs):
                for root, dirs, files in os.walk(resource_docs):
                    # 过滤掉.开头的文件夹
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for file in files:
                        if not file.startswith('.'):  # 过滤掉.开头的文件
                            ext = os.path.splitext(file)[1][1:]
                            if ext in extensions:
                                name = os.path.splitext(file)[0]
                                desc = f"{self._get_resource_type(ext)}资源名: {os.path.join(root, file)}, 资源说明: {name}"
                                self.add_knowledge(desc)

    def add_resource(self, resource_name: str, description: str=None):
        """
        添加资源信息到知识库中。
        """
        ext = os.path.splitext(resource_name)[1][1:]
        resource_type = self._get_resource_type(ext)
        self.add_knowledge(f"资源名: {resource_name}, 资源类型: {resource_type}, 资源说明: {description}")

    def add_knowledge(self, item: Union[str, Document, VectorDB, Retriever]):
        """
        添加知识信息到知识库中。
        """
        if isinstance(item, (str, Document, VectorDB, Retriever)):
            self.knowledge.add(item)
        else:
            raise ValueError("Knowledge MUST be a string, Document or VectorDB")

    def get_knowledge(self, query: str=None, verbose: bool=False):
        """
        根据知识清单召回知识，并返回知识文本列表。
        """
        knowledge = []
        self._recalled_knowledge.clear()
        for kg in self.knowledge:
            if isinstance(kg, Document):
                knowledge.append(kg.text)
                self._recalled_knowledge.append(kg)
            elif isinstance(kg, str):
                knowledge.append(kg)
                self._recalled_knowledge.append(kg)
            elif isinstance(kg, (VectorDB, Retriever)):
                docs = kg(query, verbose=verbose)
                self._recalled_knowledge.extend(docs)
                knowledge.append("\n\n".join([doc.text for doc in docs]))
            else:
                raise ValueError("Knowledge MUST be a string, Document or VectorDB")
        return knowledge

    def clone_chat_learn(self, dest: str, src: str=None):
        """
        克隆 illufly 自身的聊天问答经验。
        """
        if not os.path.exists(dest):
            os.makedirs(dest)

        files_count = 0
        src = src or get_env("ILLUFLY_CHAT_LEARN")
        for item in os.listdir(src):
            if item.startswith('.'):
                continue
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dest, item)
            if os.path.isdir(src_path):
                # 如果是目录，递归拷贝
                self.clone_chat_learn(dst_path, src_path)
            else:
                # 如果是文件，直接拷贝
                shutil.copy2(src_path, dst_path)
                files_count += 1
        return f"从 {src} 拷贝到 {dest} 完成，共克隆了 {files_count} 个文件。"

    def clear_chat_learn(self):
        """
        清空聊天问答经验。
        """
        src = get_env("ILLUFLY_CHAT_LEARN")
        if os.path.exists(src):
            shutil.rmtree(src)
