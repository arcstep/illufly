from .base import Runnable
from ...io import EventBlock
from ...utils import minify_text

class Importer(Runnable):
    """
    文档导入。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def call(self, text: str, **kwargs):
        self._last_output = text
        yield EventBlock("chunk", minify_text(text))
