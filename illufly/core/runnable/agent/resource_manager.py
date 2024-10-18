import re
from typing import Any, Set, Union, List, Dict
from ...document import Document
from ..vectordb import VectorDB
from ..message import Message

class ResourceManager:
    @classmethod
    def available_params(cls):
        """
        返回当前可用的参数列表。
        """
        return {
            "resources": "资源列表",
        }

    def __init__(self, resources: List[Any] = None):
        """
        管理智能体使用到的图片、视频、音频、数据、文档等资源。
        """
        self.resources = []
        for r in (resources or []):
            self.add_resource(r)

    def add_resource(self, *content: Union[str, List[Any], Dict[str, str]]):
        for c in content:
            if isinstance(c, str): 
                self.resources.append(Message(role="resource", content=[{"text": c}]))
            elif isinstance(c, dict):
                self.resources.append(Message(role="resource", content=[{k:v} for k, v in c.items()]))
            elif isinstance(c, list):
                self.resources.append(Message(role="resource", content=c))
            else:
                raise ValueError("Resource must be a string or a dict")

    def add_images(self, description: str, images: List[str]):
        if not isinstance(images, list):
            images = [images]
        new_rc = Message(role="resource", content=[{"image": image} for image in images] + [{"text": description}])
        if self.get_signature(new_rc) in [self.get_signature(r) for r in self.resources]:
            return None
        else:
            self.resources.append(new_rc)
            return new_rc

    def get_signature(self, message: Message):
        texts = []
        for x in message.content:
            for v in x.values():
                texts.append(v)
        return "__".join(texts)

    def to_messages(self, style: str="qwen_vl"):
        return [r.to_dict(style=style) for r in self.resources]

    def clear_resources(self):
        self.resources.clear()

    def get_text(self):
        return [r.to_dict(style="text")['content'] for r in self.resources]
    
    def get_resources(self, query: str=None):
        """
        获取资源描述。
        """
        resources = []
        for r in self.to_messages():
            if r['role'] == "resource":
                text_descriptions = []
                images = []
                audios = []
                videos = []
                for items in r['content']:
                    for k, v in items.items():
                        if k == 'text':
                            text_descriptions.append(v)
                        elif k == 'image':
                            images.append(v)
                        elif k == 'audio':
                            audios.append(v)
                        elif k == 'video':
                            videos.append(v)
                desc = "resource: "
                if len(images) > 0:
                    desc += "[图片] " + " ".join(images) + ", "
                if len(audios) > 0:
                    desc += "[音频] " + " ".join(audios) + ", "
                if len(videos) > 0:
                    desc += "[视频] " + " ".join(videos) + ", "
                if len(text_descriptions) > 0:
                    desc += ", ".join(text_descriptions)
                resources.append(desc)
        return resources
