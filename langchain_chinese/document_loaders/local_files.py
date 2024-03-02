import os
from typing import Iterator, List, Union
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders.base import BaseLoader
from langchain_community.document_loaders import Docx2txtLoader

class LocalFilesLoader(BaseLoader):
    """
    Load Local files as Documents.
    
    Support:
        - TXT
        - Markdown
        - Htmls
        - Word
        - PDF
    """
    
    documents_folder: str = None
    """Specify the local target folder to load"""
    
    includes: List[str] = []
    """Only include the folders or files"""

    excludes: List[str] = []
    """Not to load the folders or files"""
    
    extensions: List[str] = ["pdf", "docx"]
    """The files with these extentions can be loaded"""

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
            self.documents_folder = documents_folder

        for key in ["includes", "excludes", "extensions"]:
            if key in kwargs:
                setattr(self, key, kwargs[key])

    def get_files(self) -> list[str]:
        """List All Files with Extension"""
        files = []
        
        # get all files defaults
        folders = self.documents_folder
        for dirpath, dirnames, filenames in os.walk(folders):
            for filename in filenames:
                if(self.extensions == []):
                    files.append(os.path.join(dirpath, filename))
                else:
                    if get_file_extension(filename) in self.extensions:
                        files.append(os.path.join(dirpath, filename))

        # filter files with includes
        if(self.includes != []):
            to_includes = [os.path.join(self.documents_folder, path) for path in self.includes]
            files = [f for f in files if any(f.startswith(include) for include in to_includes)]

        # filter files with excludes
        if(self.excludes != []):
            to_excludes = [os.path.join(self.documents_folder, path) for path in self.excludes]
            files = [f for f in files if not any(f.startswith(exclude) for exclude in to_excludes)]
        
        return files
    
    def load_docs(self, filename: str) -> List[Document]:
        """Load file as Documents by FileLoadFactory"""
        file_loader = FileLoadFactory.get_loader(filename)
        pages = file_loader.load()
        return pages

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
            return PyPDFLoader(filename)
        elif ext == "docx":
            return Docx2txtLoader(filename)
        else:
            raise NotImplementedError(f"File extension {ext} not supported now.")
    
def get_file_extension(filename: str) -> str:
    """Get File Extension"""
    return filename.split(".")[-1]
    