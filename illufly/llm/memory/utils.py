from datetime import datetime
import random

def generate_key(*args) -> str:
    """生成ID前缀"""
    return ".".join(args)

def generate_id() -> str:
    """生成ID"""
    timestamp = datetime.now().timestamp()
    return f"{int(timestamp):010d}.{int((timestamp - int(timestamp)) * 1000000):06d}"
