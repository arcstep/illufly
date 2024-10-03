from typing import Dict, Any
from ..utils import minify_text
import json
import uuid

class Document():
    def __init__(self, text: str=None, index: str=None, metadata: Dict[str, Any] = None):
        self.text = text or ""
        self.index = index or ""
        self.metadata = {'source': 'unknown', **(metadata or {})}
        if 'id' not in self.metadata:
            self.metadata['id'] = str(uuid.uuid4())

    def __repr__(self):
        return f"Document(text='{minify_text(self.text)}', metadata='{minify_text(json.dumps(self.metadata, ensure_ascii=False))}')"

    def __str__(self):
        return self.text
    
    def __len__(self):
        return len(self.text)
