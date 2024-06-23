from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.runnables import Runnable
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from ..config import get_folder_root, get_folder_public, get_folder_docs, get_default_env
from ..utils import raise_not_install
from ..writing.markdown import MarkdownLoader

import os
import re
import sys
# import subprocess

def get_file_extension(filename: str) -> str:
    """Get File Extension"""
    return filename.split(".")[-1].lower()

class FileLoadFactory:
    @staticmethod
    def get_loader(filename):
        ext = get_file_extension(filename)
        if ext == "md":
            return MarkdownLoader(filename)
        elif ext == "pdf":
            try:
                import pypdf
                return PyPDFLoader(filename)
            except BaseException as e:
                raise_not_install('pypdf')
        elif ext == "docx":
            try:
                import docx2txt
                return Docx2txtLoader(filename)
            except BaseException as e:
                raise_not_install('docx2txt')
        elif ext == "xlsx":
            try:
                import unstructured
                return UnstructuredExcelLoader(filename, mode="elements")
            except BaseException as e:
                raise_not_install('unstructured')
        elif ext == "txt":
            return TextLoader(filename, autodetect_encoding=True)
        else:
            print(f"WARNING: Loaded File extension {ext} not supported now.")

        return None

class LocalFilesLoader(BaseLoader):
    """
    从本地文件中检索知识文档，支持docx、pdf、txt、md、xlsx等文档。
    
    过滤目标：
    - 根目录：由 TEXTLONG_DOCS 变量指定
    - 过滤目标：文件全路径移除 TEXTLONG_DOCS 部份后剩余的部份
    
    过滤规则包含：
    - 目录过滤：由 included_prefixes 指定，以列表中的字符串开头就保留
    - 目录排除：由 excluded_prefixes 指定，以列表中的字符串开头就排除
    - 路径过滤：由 path_regex 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 扩展名过滤：由 extensions 指定，即文件 xxx.ext 的末尾 ext
    """

    def __init__(
        self,
        llm: Runnable,
        project_folder: str=None,
        user_id: str=None,
        path_regex: str=None,
        included_prefixes: List[str] = [],
        excluded_prefixes: List[str] = [],
        extensions: List[str] = [],
        *args, **kwargs
    ):
        self.user_id = user_id or get_folder_public()
        self.project_folder = project_folder or get_folder_docs()
        self.path_regex = path_regex or ".*"
        self.included_prefixes = included_prefixes
        self.excluded_prefixes = excluded_prefixes
        self.extensions = extensions or ["docx", "pdf", "md", "txt", "xlsx"]
        self.documents_folder = os.path.join(get_folder_root(), self.user_id, self.project_folder)
    
    def help(self):
        return "\n".join([
            item for item in [
                f"支持为 <{self.user_id}> 从 [{self.documents_folder}] 中加载类型为 {','.join(self.extensions)} 的文件。",
                f"路径规则应当符合 [{self.path_regex}] 的正则表达式规则检查" if self.path_regex != ".*" else "",
                f"但仅包含以 [{self.included_prefixes}] 开始的文件夹" if self.included_prefixes else "",
                f"但必须排除以 [{self.excluded_prefixes}] 开始的文件夹" if self.excluded_prefixes else "",
            ] if item != ""
        ])

    def get_files(self) -> list[str]:
        """
        按照规则设定过滤本地资料文件。
        
        如果希望按自定义逻辑处理每一个文件，可以直接使用这个方法。
        """
        files = []

        folders = self.documents_folder
        for dirpath, dirnames, filenames in os.walk(folders):
            for filename in filenames:
                relpath = os.path.relpath(os.path.join(dirpath, filename), folders)
                if relpath.startswith(".") or re.search('/.', relpath):
                    # 确保不包含以.开头的文件夹或文件
                    continue
                if self.included_prefixes and not any(relpath.startswith(include) for include in self.included_prefixes):
                    continue
                if self.excluded_prefixes and any(relpath.startswith(exclude) for exclude in self.excluded_prefixes):
                    continue
                if self.path_regex and not re.search(self.path_regex, relpath):
                    continue
                if self.extensions and get_file_extension(filename) not in self.extensions:
                    continue
                files.append(os.path.join(dirpath, filename))

        return files

    def load_docs(self, filename: str) -> List[Document]:
        """
        按照文档类型加载文档，并直输出循环拆分后的文档块。
        """
        file_loader = FileLoadFactory.get_loader(filename)
        if file_loader:
            file_docs = file_loader.load()
            text = '\n'.join([doc.page_content for doc in file_docs])
            blocked_docs = [Document(page_content=text, metadata={"source": filename})]

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size = get_default_env("TEXTLONG_DOC_CHUNK_SIZE"),
                chunk_overlap = get_default_env("TEXTLONG_DOC_CHUNK_OVERLAP"),
                length_function = len,
                is_separator_regex = False,
            )
            return text_splitter.split_documents(blocked_docs)
        else:
            return []

    def lazy_load(self) -> Iterator[Document]:
        """
        为每个文件重新分配块结构。
        """
        for filename in self.get_files():
            file_docs = self.load_docs(filename)
            for doc in file_docs:
                yield doc

    def load(self) -> List[Document]:
        """
        如果直接使用这个方法，将会直接调用load_docs方法。
        
        默认的load_docs方法会将文档做整体切分，然后直接输出。
        这不是最优的RAG处理方式，但足够简单。
        """
        return list(self.lazy_load())

    def get_embeddings(self):
        """
        获得缓存的向量编码。
        """
        pass
