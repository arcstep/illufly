from ..community.zhipu import ZhipuEmbeddings
from ..community.dashscope import TextEmbeddings
from ..community.openai import OpenAIEmbeddings
from ..community.hugging_face import HuggingFaceEmbeddings

__all__ = [
    "ZhipuEmbeddings",
    "TextEmbeddings",
    "OpenAIEmbeddings",
    "HuggingFaceEmbeddings",
]
