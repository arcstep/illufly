import os
import fnmatch
from ..types import Markdown, Document, TextBlock
from ..core.runnable import Importer

class MarkdownFileImporter(Importer):
    def __init__(self, dir: str = '.', filter: str = '*', exts: list = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = dir
        self.filename_filter = filter
        self.extensions = exts or ['*.md', '*.markdown', '*.MD', '*.MARKDOWN']
        self.documents = []
    
    @property
    def last_output(self):
        return self.documents

    def call(self, **kwargs) -> Markdown:
        """
        将文件作为 markdown 文本导入。
        """
        self.documents.clear()

        files = self.get_files(self.directory, self.filename_filter, self.extensions)
        for file in files:
            try:
                if os.path.exists(file):
                    with open(file, 'r', encoding='utf-8') as f:
                        txt = f.read()
                        yield TextBlock("chunk", compress_text(txt))
                        markdown = Markdown(txt, source=file)
                        self.documents.extend(markdown.split())
            except Exception as e:
                yield("warn", f"无法读取文件 {file}: {e}")

    def get_files(self, directory, filename_filter, extensions):
        matches = []
        for root, dirnames, filenames in os.walk(directory):
            for extension in extensions:
                for filename in fnmatch.filter(filenames, filename_filter + extension):
                    matches.append(os.path.join(root, filename))
        return matches

