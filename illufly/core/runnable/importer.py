from .base import Runnable
from ...io import TextBlock
from ...utils import compress_text

class Importer(Runnable):
    """
    导入器。
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def call(self, text: str, **kwargs):
        self._last_output = text
        yield TextBlock("chunk", compress_text(text))
