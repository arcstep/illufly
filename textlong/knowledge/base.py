from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders import (
    TextLoader,
    PyPDFLoader,
    Docx2txtLoader,
    UnstructuredMarkdownLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.embeddings import Embeddings
from langchain_core.runnables import Runnable
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders.excel import UnstructuredExcelLoader
from ..config import (
    get_folder_root,
    get_folder_public,
    get_folder_docs,
    get_default_env,
    get_cache_embeddings,
    get_info_color,
    get_text_color,
    get_chunk_color,
    get_warn_color
)
from ..utils import raise_not_install, hash_text, clean_filename
from ..writing.markdown import MarkdownLoader

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
            info = f"WARNING: Loaded File extension {ext} not supported now."
            print(get_warn_color() + info + "\033[0m")

        return None

class LocalFilesLoader(BaseLoader):
    """
    从本地文件中检索知识文档，支持docx、pdf、txt、md、xlsx等文档。
    
    文档位置：
    - 加载文档的位置由 {base_folder} 指定，允许用列表指定多个（没有指定就选用 {TEXTLONG_DOCS} 环境变量）
    - 文本嵌入的缓存 {cache_folder} 默认是第一个 {base_folder}，也可以专门指定
    
    过滤规则包含：
    - 按目录开头过滤：由 included_prefixes 指定，以列表中的字符串开头就保留
    - 按目录开头排除：由 excluded_prefixes 指定，以列表中的字符串开头就排除
    - 按路径正则匹配：由 path_regex 指定，应当是正则表达式，通常作为文件的过滤规则使用
    - 按扩展名过滤文件：由 extensions 指定，默认为 ["docx", "pdf", "md", "txt", "xlsx"]
    """

    def __init__(
        self,
        base_folder: Union[str, List[str]]=None,
        cache_folder: str=None,
        path_regex: str=None,
        included_prefixes: List[str] = [],
        excluded_prefixes: List[str] = [],
        extensions: List[str] = [],
        *args, **kwargs
    ):
        if isinstance(base_folder, str):
            self.base_folders = [base_folder]
        elif isinstance(base_folder, list):
            self.base_folders = base_folder
        elif base_folder == None:
            self.base_folders = [get_folder_docs()]
        else:
            raise(ValueError("base_folder: MUST be str or list[str]: ", base_folder))

        self.cache_folder = cache_folder or self.base_folders[0]

        self.path_regex = path_regex or ".*"
        self.included_prefixes = included_prefixes
        self.excluded_prefixes = excluded_prefixes
        self.extensions = extensions or ["docx", "pdf", "md", "txt", "xlsx"]
    
    def get_files(self) -> list[str]:
        """
        按照规则设定过滤本地资料文件。
        """
        files = []

        documents_folders = [os.path.join(get_folder_root(), folder) for folder in self.base_folders]
        for folders in documents_folders:
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

    def cache_embeddings(self, model: Embeddings, tag_name: str=None):
        """
        缓存文本嵌入。
        
        tag_name 支持按不同模型厂商或模型名称缓存到子目录。
        """
        vector_folder = os.path.join(self.cache_folder, get_cache_embeddings(), (tag_name or ""))

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
                    info = f'<{source}> {text[0:50]}{"..." if len(text) > 50 else ""}'
                    print(get_info_color() + info + "\033[0m")

            info = f'Cached {len(to_embedding_paths)} embeddings to {vector_folder} !'
            print(get_info_color() + info + "\033[0m")
            return True
        
        print(get_info_color() + f'No embeddings to cached!' + "\033[0m")
        return False

    def load_embeddings(self, model: Embeddings=None, tag_name: str=None):
        """
        缓存文本嵌入。
        """
        vector_folder = os.path.join(self.cache_folder, get_cache_embeddings(), (tag_name or ""))

        texts = []
        vectors = []
        metadatas = []
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
                    metadatas.append(metadata)
            else:
                info = f'No embeddings cache found for: <{source}> {text[0:50]}{"..." if len(text) > 50 else ""}'
                print(get_warn_color() + info + "\033[0m")

        return list(zip(texts, vectors)), model, metadatas
