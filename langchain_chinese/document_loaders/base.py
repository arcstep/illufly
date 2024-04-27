from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import Docx2txtLoader
from langchain_community.document_loaders import UnstructuredMarkdownLoader

import os
import re

class BaseQALoader(BaseLoader):
    """
    从本地文件中检索知识文档。
    
    包含的过滤规则有：
    - 从 LANGCHAIN_CHINESE_DOCUMENTS_FOLDER 变量指定的路径列举文件
    - 按照 question_filter 过滤文档路径，但不要过滤 LANGCHAIN_CHINESE_DOCUMENTS_FOLDER 指定的部份
    - 按照 extensions 过滤指定扩展名的文件
    """
    
    # support types
    extensions: List[str] = ["docx", "pdf", "md"]
    
    # root document folder storage
    _documents_folder: str = "./documents"
    
    @property
    def documents_folder(self):
        return self._documents_folder

    @documents_folder.setter
    def documents_folder(self, value):
        self._documents_folder = os.path.abspath(value)

    # question file filter
    question_filter: str = ".*"
    
    # answer file filter
    answer_filter: str = ".*"
    
    # only include folder or files
    _includes: List[str] = []

    @property
    def includes(self):
        return self._includes

    @includes.setter
    def includes(self, value):
        if(value is not None and value != []):
            self._includes = [os.path.abspath(os.path.join(self.documents_folder, f)) for f in value]

    # excludes folder or files
    _excludes: List[str] = []

    @property
    def excludes(self):
        return self._excludes

    @excludes.setter
    def excludes(self, value):
        if(value is not None and value != []):
            self._excludes = [os.path.abspath(os.path.join(self.documents_folder, f)) for f in value]

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

        for key in ["extensions", "includes", "excludes", "question_filter", "answer_filter"]:
            if(kwargs.get(key) is not None):
                setattr(self, key, kwargs.get(key))

    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = []

        # get all files defaults
        folders = self.documents_folder
        print(f"question_filter: {self.question_filter}")
        print(f"extensions: {self.extensions}")
        for dirpath, dirnames, filenames in os.walk(folders):
            print("-"*20)
            print(dirpath, filenames)
            for filename in filenames:
                relpath = os.path.relpath(os.path.join(dirpath, filename), folders)
                if(self.extensions == []):
                    if re.search(self.question_filter, relpath):
                        files.append(os.path.join(dirpath, filename))
                else:
                    if get_file_extension(filename) in self.extensions and re.search(self.question_filter, relpath):
                        files.append(os.path.join(dirpath, filename))
                print(relpath)
                print(files)

        # filter files with includes
        if(self.includes != []):
            print(f"include folders: {self.excludes}")
            files = [f for f in files if any(f.startswith(include) for include in self.includes)]
            print(files)

        # filter files with excludes
        if(self.excludes != []):
            print(f"exclude folders: {self.excludes}")
            files = [f for f in files if not any(f.startswith(exclude) for exclude in self.excludes)]
            print(files)

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

class FileLoadFactory:
    @staticmethod
    def get_loader(filename: str):
        filename = filename.strip()
        ext = get_file_extension(filename)
        if ext == "pdf":
            loader = PyPDFLoader(filename)
            return loader
        elif ext == "docx":
            loader = Docx2txtLoader(filename)
            return loader
        elif ext == "md":
            loader = UnstructuredMarkdownLoader(
                filename, mode="elements", strategy="fast",
            )
            return loader
        else:
            print(f"WARNING: Loaded File extension {ext} not supported now.")
            return None

def get_file_extension(filename: str) -> str:
    """Get File Extension"""
    return filename.split(".")[-1]


class LocalFilesLoader(BaseQALoader):
    """
    Load Local files as Documents.
    """
    question_filter = ".*"
    knowledge_filter = ".*"

class AnswerQALoader(BaseQALoader):
    """
    Load Answer as Documents.
    """
    question_filter = "input.md"
    knowledge_filter = "answer.md"

class ExampleQALoader(BaseQALoader):
    """
    Load Example as Documents.
    """
    question_filter = "input.md"
    knowledge_filter = "example.md"
