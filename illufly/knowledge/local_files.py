from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import Runnable
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from langchain_text_splitters import TextSplitter

from ..config import get_folder_root, get_env
from ..utils import raise_not_install, hash_text, clean_filename
from ..project import is_project_existing, BaseProject
from ..writing import MarkdownLoader
from ..io import TextBlock

from .qa_excel import QAExcelsLoader

import os
import re
import sys
import pickle
# import subprocess

def collect_docs(docs: List[str]) -> str:
    """
    如果 Document 中包含的 metadata['answer'] 属性就优先采纳。
    """
    return "\n-----------------------------------\n".join([
        d.page_content + "\n" + d.metadata['answer'] if 'answer' in d.metadata else d.page_content
        for d in docs
    ])

def get_file_extension(filename: str) -> str:
    """Get File Extension"""
    return filename.split(".")[-1].lower()

class FileLoadFactory:
    @staticmethod
    def get_loader(filename):
        ext = get_file_extension(filename)
        if ext == "md":
            return MarkdownLoader(filename)
        elif ext == "xlsx":
            return QAExcelsLoader(filename)
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
        elif ext == "txt":
            return TextLoader(filename, autodetect_encoding=True)
        else:
            info = f"WARNING: Loaded File extension {ext} not supported now."
            print(get_warn_color() + info + "\033[0m")

        return None

class LocalFilesLoader(BaseLoader):
    """
    从本地文件中检索知识文档，支持docx、pdf、txt、md、xlsx等文档。
    
    文档位置：
    - 加载文档的位置由 {docs_folders} 指定，允许用列表指定多个（没有指定就选用 {ILLUFLY_DOCS} 环境变量）
    - {docs_folders} 应当描述为相对于 {base_folder} 的相对位置
    - 文本嵌入的缓存 {cache_folder} 默认是 {base_folder}，也可以专门指定
    
    过滤规则包含：
    - 按目录开头过滤：由 included_prefixes 指定，以列表中的字符串开头就保留
    - 按目录开头排除：由 excluded_prefixes 指定，以列表中的字符串开头就排除
    - 按路径正则匹配：由 path_regex 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 按扩展名过滤文件：由 extensions 指定，默认为 ["docx", "pdf", "md", "txt", "xlsx"]
    """

    def __init__(
        self,
        docs_folders: Union[str, List[str]]=None,
        cache_folder: str=None,
        path_regex: str=None,
        included_prefixes: List[str] = [],
        excluded_prefixes: List[str] = [],
        extensions: List[str] = [],
        base_folder: str=None,
        text_spliter: TextSplitter=None,
        *args, **kwargs
    ):
        if isinstance(docs_folders, str):
            self.docs_folders = [docs_folders]
        elif isinstance(docs_folders, list):
            self.docs_folders = docs_folders
        elif docs_folders == None:
            self.docs_folders = [get_env("ILLUFLY_DOCS")]
        else:
            raise(ValueError("base_folder: MUST be str or list[str]: ", base_folder))

        self.base_folder = base_folder or get_folder_root()
        self.cache_folder = cache_folder or self.base_folder

        self.path_regex = path_regex or ".*"
        self.included_prefixes = included_prefixes
        self.excluded_prefixes = excluded_prefixes
        self.extensions = extensions or ["docx", "pdf", "md", "txt", "xlsx"]

        self.text_spliter = text_spliter
    
    def get_files(self) -> list[str]:
        """
        按照规则设定过滤本地资料文件。
        """
        files = []

        documents_folders = [os.path.join(self.base_folder, folder) for folder in self.docs_folders]
        for folder in documents_folders:
            if is_project_existing(folder):
                project = BaseProject(folder, self.base_folder)
                files.extend(list(project.embedding_files))
            else:
                for dirpath, dirnames, filenames in os.walk(folder):
                    for filename in filenames:
                        relpath = os.path.relpath(os.path.join(dirpath, filename), folder)
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
            return file_loader.load_and_split(self.text_spliter)
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

    def cache_embeddings(self, model: Embeddings, tag_name: str=None):
        """
        缓存文本嵌入。
        
        tag_name 支持按不同模型厂商或模型名称缓存到子目录。
        """
        tag_name = tag_name or ''
        cache_folder = get_env("ILLUFLY_CACHE_EMBEDDINGS")
        vector_folder = os.path.join(self.cache_folder, cache_folder, tag_name)

        to_embedding_texts = []
        to_embedding_paths = []

        docs = self.load()
        all_docs = [
            (
                d.page_content,
                (clean_filename(d.metadata['source']) if 'source' in d.metadata else '')
            )
            for d
            in docs
        ]

        for text, source in all_docs:
            vector_path = hash_text(text) + ".emb"
            cache_path = os.path.join(vector_folder, source, vector_path)
            if not os.path.exists(cache_path):
                to_embedding_texts.append(text)
                to_embedding_paths.append(cache_path)

        if to_embedding_texts and len(to_embedding_texts) == len(to_embedding_paths):
            vectors = model.embed_documents(to_embedding_texts)
            for cache_path, text, data in list(zip(to_embedding_paths, to_embedding_texts, vectors)):
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'wb') as f:
                    pickle.dump(data, f)
                    chunk = TextChunk('info', f'<{source}> {text[0:50]}{"..." if len(text) > 50 else ""}')
                    print(chunk.text_with_print_color)

            chunk = TextChunk('info', f'Cached {len(to_embedding_paths)} embeddings to {vector_folder} !')
            print(chunk.text_with_print_color)
            return True
        
        return False

    def load_embeddings(self, model: Embeddings=None, tag_name: str=None):
        """
        缓存文本嵌入。
        """
        tag_name = tag_name or ''
        cache_folder = get_env("ILLUFLY_CACHE_EMBEDDINGS")
        vector_folder = os.path.join(self.cache_folder, cache_folder, tag_name)

        texts = []
        vectors = []
        metadata_list = []
        to_embedding_paths = []

        docs = self.load()
        all_docs = [
            (
                d.page_content,
                (clean_filename(d.metadata['source']) if 'source' in d.metadata else ''),
                d.metadata
            )
            for d
            in docs
        ]

        for text, source, metadata in all_docs:
            vector_path = hash_text(text) + ".emb"
            cache_path = os.path.join(vector_folder, source, vector_path)
            if os.path.exists(cache_path):
                with open(cache_path, 'rb') as f:
                    texts.append(text)
                    vectors.append(pickle.load(f))
                    metadata_list.append(metadata)
            else:
                chunk = TextChunk('warn', f'No embeddings cache found for: <{source}> {text[0:50]}{"..." if len(text) > 50 else ""}')
                print(chunk.text_with_print_color)

        return list(zip(texts, vectors)), model, metadata_list
