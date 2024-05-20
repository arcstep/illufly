from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from ..config import get_textlong_folder, _DOCS_FOLDER_NAME

import os
import re
import sys
# import subprocess

def raise_not_install(packages):
    print(f"please install package: '{packages}' with pip or poetry")
    # auto install package
    # subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])

def get_file_extension(filename: str) -> str:
    """Get File Extension"""
    return filename.split(".")[-1].lower()

class FileLoadFactory:
    @staticmethod
    def get_loader(filename):
        ext = get_file_extension(filename)
        if ext == "pdf":
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
        elif ext == "md":
            try:
                import unstructured
                import markdown
                return UnstructuredMarkdownLoader(filename, mode="elements", strategy="fast")
            except BaseException as e:
                raise_not_install(['markdown', 'unstructured'])
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
    - 根目录：由 LANGCHAIN_CHINESE_DOCUMENTS_FOLDER 变量指定
    - 过滤目标：文件全路径移除 LANGCHAIN_CHINESE_DOCUMENTS_FOLDER 部份后剩余的部份
    
    过滤规则包含：
    - 目录过滤：由 included_prefixes 指定，以列表中的字符串开头就保留
    - 目录排除：由 excluded_prefixes 指定，以列表中的字符串开头就排除
    - 路径过滤：由 path_regex 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 扩展名过滤：由 extensions 指定，即文件 xxx.ext 的末尾 ext
    """

    def __init__(
        self,
        user_id: str=None,
        path_regex: str=None,
        included_prefixes: List[str] = [],
        excluded_prefixes: List[str] = [],
        extensions: List[str] = [],
        *args, **kwargs
    ):
        self.user_id = user_id or "public"
        self.path_regex = path_regex or ".*"
        self.included_prefixes = included_prefixes
        self.excluded_prefixes = excluded_prefixes
        self.extensions = extensions or ["docx", "pdf", "md", "txt", "xlsx"]
        self.documents_folder = os.path.join(get_textlong_folder(), self.user_id, _DOCS_FOLDER_NAME)

    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = []

        folders = self.documents_folder
        for dirpath, dirnames, filenames in os.walk(folders):
            for filename in filenames:
                relpath = os.path.relpath(os.path.join(dirpath, filename), folders)
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
        """Load file as Documents by FileLoadFactory"""
        file_loader = FileLoadFactory.get_loader(filename)
        if file_loader:
            pages = file_loader.load()
            return pages
        else:
            return []

    def lazy_load(self) -> Iterator[Document]:
        """Load files as Documents by FileLoadFactory"""
        for filename in self.get_files():
            for doc in self.load_docs(filename):
                yield doc

    def load(self) -> List[Document]:
        """Load Documents from All Files."""
        return list(self.lazy_load())
