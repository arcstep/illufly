from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders import TextLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader

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
    - 目录过滤：由 includes 指定，以列表中的字符串开头就保留
    - 目录排除：由 excludes 指定，以列表中的字符串开头就排除
    - 路径过滤：由 path_filter 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 扩展名过滤：由 extensions 指定，即文件 xxx.ext 的末尾 ext
    """
    
    # support types
    extensions: List[str] = ["docx", "pdf", "md", "txt", "xlsx"]
    
    # root document folder storage
    _documents_folder: str = "./documents"
    
    @property
    def documents_folder(self):
        return self._documents_folder

    @documents_folder.setter
    def documents_folder(self, value):
        self._documents_folder = os.path.abspath(value)

    # question path filter
    path_filter: str = ".*"

    # only include folder or files
    includes: List[str] = []

    # excludes folder or files
    excludes: List[str] = []

    def __init__(
        self,
        documents_folder: str = None,
        *args, **kwargs
    ):
        """Initialize with API token and the URLs to scrape"""
        if(documents_folder is None):
            _documents_folder = os.getenv("LANGCHAIN_CHINESE_DOCUMENTS_FOLDER")
            if(_documents_folder is not None):
                self.documents_folder = _documents_folder
            else:
                self.documents_folder = "./documents"
        else:
            self.documents_folder = documents_folder

        for key in ["extensions", "includes", "excludes", "path_filter"]:
            if(kwargs.get(key) is not None):
                setattr(self, key, kwargs.get(key))

    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = []

        folders = self.documents_folder
        for dirpath, dirnames, filenames in os.walk(folders):
            for filename in filenames:
                relpath = os.path.relpath(os.path.join(dirpath, filename), folders)
                if self.includes and not any(relpath.startswith(include) for include in self.includes):
                    continue
                if self.excludes and any(relpath.startswith(exclude) for exclude in self.excludes):
                    continue
                if self.path_filter and not re.search(self.path_filter, relpath):
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

class LocalFilesQALoader(LocalFilesLoader):
    """
    指定引用源过滤，就可以实现QA对分离的知识查询：
      即根据问题的文本相似度查询文档中的Question部份，
      但根据Question结果的source部份查询匹配的Anwser，作为LLM的参考结果。
    """
    answer_file: str = ["answer.md", "example.md"]

    def __init__(
        self,
        documents_folder: str = None,
        *args, **kwargs
    ):
        super().__init__(documents_folder, *args, **kwargs)

        for key in ["answer_file"]:
            if(kwargs.get(key) is not None):
                setattr(self, key, kwargs.get(key)) 

    def get_answer(self, doc: Union[str, Document]):
        """
        根据Q文档中Document.meatadata['source']部份的路径，获得匹配的A文档
        """
        if isinstance(doc, str):
            dirpath = os.path.dirname(doc)
        elif isinstance(doc, Document):
            dirpath = os.path.dirname(doc.metadata['source'])
        else:
            raise TypeError("doc must be a str or a Document")

        answers = {}
        for answer_file in self.answer_file:
            target = os.path.join(dirpath, answer_file)
            if os.path.exists(target):
                answer_key = os.path.splitext(answer_file)[0]
                answer_content = [doc.page_content for doc in self.load_docs(target)]
                answers[answer_key] = answer_content
        return answers
    
    # 加载文档内容时排除 answer_file
    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = super().get_files()
        files = [f for f in files if os.path.basename(f) not in self.answer_file]
        return files