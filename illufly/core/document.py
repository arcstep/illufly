from typing import Dict, Any
from ..utils import compress_text
import json

class Document():
    def __init__(self, text: str, metadata: Dict[str, Any] = None):
        self.text = text or ""
        self.metadata = metadata or {'source': 'unknown'}

    def __repr__(self):
        return f"Document(text='{compress_text(self.text)}', metadata='{compress_text(json.dumps(self.metadata))}')"

    def __str__(self):
        return self.text
