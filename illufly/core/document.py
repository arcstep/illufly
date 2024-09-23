from typing import Dict, Any
from ..utils import minify_text
import json

class Document():
    def __init__(self, text: str, metadata: Dict[str, Any] = None):
        self.text = text or ""
        self.metadata = {'source': 'unknown', **(metadata or {})}

    def __repr__(self):
        return f"Document(text='{minify_text(self.text)}', metadata='{minify_text(json.dumps(self.metadata, ensure_ascii=False))}')"

    def __str__(self):
        return self.text
