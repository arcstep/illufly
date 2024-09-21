import os
from ..types import Markdown, Document, TextBlock
from ..core.runnable import Importer

class MarkdownFileImporter(Importer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def call(self, file_path: str=None, **kwargs) -> Markdown:
        """
        将文件作为 markdown 文本导入。
        """

        txt = None
        if file_path:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    txt = f.read()
                    self._output = txt
                    yield TextBlock("chunk", compress_text(txt))
        
        self._output = Markdown(txt).split()
