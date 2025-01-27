from datetime import datetime
import random

def generate_id(title: str, user_id: str, thread_id: str) -> str:
    """生成ID"""
    return f"{title}.{user_id}.{thread_id}.{datetime.timestamp(datetime.now())}.{random.randint(1000,9999)}"