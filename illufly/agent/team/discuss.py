from typing import List, Union

from ...io import TextBlock
from ...utils import compress_text
from ..base import Runnable
from ..chat import ChatAgent

class Discuss(Runnable):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, outline: str, *args, **kwargs):
        pass