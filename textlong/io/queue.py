from typing import Callable
import json
import multiprocessing
from .base import BaseLog
from .block import TextBlock
from .json import merge_blocks_by_index

class QueueLog(BaseLog):
    def __init__(self, queue: multiprocessing.Queue=None, timeout: int=None, *args, **kwargs):
        self.queue = queue or multiprocessing.Queue()
        self.timeout = isinstance(timeout, int) or 30
    
    def __str__(self):
        return self.queue.__str__()

    def __repr__(self):
        return f"QueueLog(queue={self.queue})"

    def __iter__(self):
        return self

    def __next__(self):
        try:
            item = self.queue.get(timeout=self.timeout)
            if item == '>-[END]>>':
                self.queue.empty()
                raise StopIteration
            return item
        except multiprocessing.queues.Empty:
            raise StopIteration

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
                self.queue.put(block)
                last_block_type = block.block_type

            if block.block_type in ['info', 'warn', 'text', 'tool_resp', 'tools_call']:
                self.queue.put(block)
                if last_block_type == "chunk":
                    last_block_type = ""
                last_block_type = block.block_type
        
        if last_block_type == "chunk":
            last_block_type = ""
        
        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            block = TextBlock("info", json.dumps(final_tools_call, ensure_ascii=False))
            self.queue.put(block)

        return {"output": output_text, "tools_call": final_tools_call}

    def end(self):
        self.queue.put('>-[END]>>')