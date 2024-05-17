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
    - 目录过滤：由 included_prefixes 指定，以列表中的字符串开头就保留
    - 目录排除：由 excluded_prefixes 指定，以列表中的字符串开头就排除
    - 路径过滤：由 path_regex 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 扩展名过滤：由 extensions 指定，即文件 xxx.ext 的末尾 ext
    """
    
    # support types
    extensions: List[str] = ["docx", "pdf", "md", "txt", "xlsx"]
    
    # 希望入库到知识库的本地文件夹根目录
    _documents_folder: str = "./documents"
    
    @property
    def documents_folder(self):
        return self._documents_folder

    @documents_folder.setter
    def documents_folder(self, value):
        self._documents_folder = os.path.abspath(value)

    # 按照该字符串（正则表达式）筛出将被入库到知识库的本地文档
    path_regex: str = ".*"

    # 只要本地文件夹的路径、子文件夹以这些列表中的字符串开头，就被入库到知识库
    included_prefixes: List[str] = []

    # 只要本地文件夹的路径、子文件夹以这些列表中的字符串开头，就被排除，不会入库到知识库
    excluded_prefixes: List[str] = []

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

        for key in ["extensions", "included_prefixes", "excluded_prefixes", "path_regex"]:
            if(kwargs.get(key) is not None):
                setattr(self, key, kwargs.get(key))

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

class LocalFilesQALoader(LocalFilesLoader):
    """
    指定引用源过滤，就可以实现QA对分离的知识查询：
      即根据问题的文本相似度查询文档中的Question部份，
      但根据Question结果的source部份查询匹配的Anwser，作为LLM的参考结果。
    """
    
    # 根据知识库查询结果的文件来源匹配关联文件，该参数可以指定这些关联文件的名称
    answer_filenames: str = ["answer.md", "example.md"]

    def __init__(
        self,
        documents_folder: str = None,
        *args, **kwargs
    ):
        super().__init__(documents_folder, *args, **kwargs)

        for key in ["answer_filenames"]:
            if(kwargs.get(key) is not None):
                setattr(self, key, kwargs.get(key)) 

    def get_answer(self, doc: Union[str, Document]):
        """
        根据Q文档中Document.meatadata['source']部份的路径，获得匹配的A文档。
        """
        if isinstance(doc, str):
            dirpath = os.path.dirname(doc)
        elif isinstance(doc, Document):
            dirpath = os.path.dirname(doc.metadata['source'])
        else:
            raise TypeError("doc must be a str or a Document")

        answers = {}
        for answer_file in self.answer_filenames:
            target = os.path.join(dirpath, answer_file)
            if os.path.exists(target):
                answer_key = self._get_answer_key(answer_file)
                answer_content = [doc.page_content for doc in self.load_docs(target)]
                answers[answer_key] = answer_content
        return answers
    
    def get_answers(self, docs: List[Union[str, Document]], answer_keys: List[str] = None):
        """
        按照Q文档查询结果和指定的keys清单，生成匹配的A文档。
        """
        all_answers = [self.get_answer(doc) for doc in docs]
        answer_file_keys = [self._get_answer_key(f) for f in self.answer_filenames]
        
        # 如果没有指定answer_keys就使用answer_filenames生成
        if answer_keys:
            answer_keys = [k for k in answer_keys if k in answer_file_keys]
        else:
            answer_keys = answer_file_keys

        # 如连answer_filenames也没有指定，就直接返回{}
        if answer_keys:
            expected_answers = {}
            for k in answer_keys:
                expected_answers.update({k: a[k] for a in all_answers if k in a})
            return expected_answers
        else:
            return {}
    
    # 重载加载文档内容：排除 answer_filenames
    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = super().get_files()
        files = [f for f in files if os.path.basename(f) not in self.answer_filenames]
        return files
    
    def _get_answer_key(self, answer_file: str):
        return os.path.splitext(answer_file)[0]