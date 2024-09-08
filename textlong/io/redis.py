from typing import Callable
import json
import redis
from .base import BaseLog
from .block import TextBlock
from .json import merge_blocks_by_index

class RedisLog(BaseLog):
    def __init__(self, redis_host='localhost', redis_port=6379, queue_name='queue_log', timeout: int=None, *args, **kwargs):
        self.redis = redis.StrictRedis(host=redis_host, port=redis_port, db=0)
        self.queue_name = queue_name
        self.timeout = timeout or 30  # 超时时间，单位为秒
    
    def __str__(self):
        host = self.redis.connection_pool.connection_kwargs['host']
        port = self.redis.connection_pool.connection_kwargs['port']
        return f"RedisLog using Redis on {host}:{port}"

    def __repr__(self):
        return f"RedisLog(redis={self.redis}, queue_name={self.queue_name})"

    def __iter__(self):
        return self

    def __next__(self):
        item = self.redis.blpop(self.queue_name, timeout=self.timeout)
        if item is None:
            raise StopIteration
        _, data = item
        if data == b'>-[END]>>':
            raise StopIteration
        item = json.loads(data)
        return TextBlock(item['block_type'], item['text'])

    def __call__(self, func: Callable, *args, **kwargs):

        output_text = ""
        tools_call = []
        last_block_type = ""

        for block in (func(*args, **kwargs) or []):
            if block.block_type in ['text', 'chunk', 'front_matter']:
                output_text += block.text
            
            if block.block_type in ['tools_call']:
                tools_call.append(json.loads(block.text))

            if block.block_type in ['chunk']:
                self.redis.rpush(self.queue_name, json.dumps({"block_type": block.block_type, "text": block.text}))
                last_block_type = block.block_type

            if block.block_type in ['info', 'warn', 'text', 'tool_resp', 'tools_call']:
                self.redis.rpush(self.queue_name, json.dumps({"block_type": block.block_type, "text": block.text}))
                if last_block_type == "chunk":
                    last_block_type = ""
                last_block_type = block.block_type
        
        if last_block_type == "chunk":
            last_block_type = ""
        
        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            block = TextBlock("info", json.dumps(final_tools_call, ensure_ascii=False))
            self.redis.rpush(self.queue_name, json.dumps({"block_type": block.block_type, "text": block.text}))

        return {"output": output_text, "tools_call": final_tools_call}

    def end(self):
        self.redis.rpush(self.queue_name, b'>-[END]>>')