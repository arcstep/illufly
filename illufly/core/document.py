from typing import Dict, Any
from ..utils import minify_text
import json

class Document():
    def __init__(self, text: str=None, audio_url: str=None, image_url: str=None, video_url: str=None, metadata: Dict[str, Any] = None):
        self.text = text or ""
        self.audio_url = audio_url or ""
        self.image_url = image_url or ""
        self.video_url = video_url or ""
        self.metadata = {'source': 'unknown', **(metadata or {})}

    def __repr__(self):
        return f"Document(text='{minify_text(self.text)}', metadata='{minify_text(json.dumps(self.metadata, ensure_ascii=False))}')"

    def __str__(self):
        return self.text
    
    def __len__(self):
        return len(self.text)
