from typing import Union, Any
import json
from ..models import (
    StreamingBlock, ReplyBlock, ErrorBlock, 
    EndBlock, RequestBlock, BaseBlock, TextChunk, MESSAGE_TYPES
)

def serialize_message(obj: Union[BaseBlock, dict]) -> bytes:
    """序列化消息，包含类型信息"""
    if isinstance(obj, BaseBlock):
        data = {
            '__type__': obj.__class__.__name__,
            'data': {
                k: v for k, v in obj.__dict__.items()
                if not k.startswith('_')  # 跳过私有属性
            }
        }
        # 特殊处理 StreamingBlock 的 content
        if isinstance(obj, StreamingBlock):
            data['data']['content'] = obj.content
    else:
        data = obj
    return json.dumps(data).encode()

def deserialize_message(data: bytes) -> Union[BaseBlock, dict]:
    """反序列化消息，根据类型信息还原对象"""
    try:
        parsed = json.loads(data.decode())
        if isinstance(parsed, dict) and '__type__' in parsed:
            msg_type = parsed['__type__']
            if msg_type in MESSAGE_TYPES:
                cls = MESSAGE_TYPES[msg_type]
                # 使用 model_validate 进行反序列化
                return cls.model_validate(parsed['data'])
        return parsed
    except Exception as e:
        raise ValueError(f"Failed to deserialize message: {e}")
