from ..envir import get_env
from .base import litellm, LiteLLM
from .retriever import ChromaRetriever
from .memory import Memory
from .chat import ChatAgent
from .thread import ThreadManager
from .models import MemoryQA, Thread, DialougeChunk, ChunkType

litellm.enable_cache(
    type="disk",
    disk_cache_dir=get_env("ILLUFLY_CACHE_LITELLM"),
    supported_call_types=["embedding", "aembedding", "atranscription", "transcription"]
)

print(get_env("ILLUFLY_CACHE_LITELLM"))

__all__ = ["litellm", "LiteLLM", "ChatAgent"]