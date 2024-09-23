import os
import fnmatch
from ..types import Markdown, Document, TextBlock
from ..core.runnable import Importer
from ..config import get_env
from ..utils import minify_text

class MarkdownFileImporter(Importer):
    def __init__(self, dir: str=None, filter: str=None, exts: list = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.directory = dir or get_env("ILLUFLY_DOCS")
        self.filename_filter = filter or '*'
        self.extensions = exts or ['*.md', '*.Md', '*.MD', '*.markdown', '*.MARKDOWN']
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
                        yield TextBlock("info", minify_text(txt))
                        markdown = Markdown(txt, source=file)
                        self.documents.extend(markdown.split())
            except Exception as e:
                yield("warn", f"读取文件失败 {file}: {e}")

    def get_files(self, directory, filename_filter, extensions):
        matches = []
        for root, dirnames, filenames in os.walk(directory):
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]  # 排除隐藏文件夹
            filenames = [f for f in filenames if not f.startswith('.')]  # 排除隐藏文件
            for extension in extensions:
                for filename in fnmatch.filter(filenames, filename_filter + extension):
                    matches.append(os.path.join(root, filename))
        return matches

