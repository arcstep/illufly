from typing import Callable
import json
import zmq
from .base import BaseLog
from .block import TextBlock
from .json import merge_blocks_by_index

class ZeroMQLog(BaseLog):
    def __init__(self, context=None, timeout: int=None, *args, **kwargs):
        self.context = context or zmq.Context()
        self.socket_push = self.context.socket(zmq.PUSH)
        self.socket_push.bind("inproc://queue")
        self.timeout = timeout or 30  # 超时时间，单位为秒

        self.socket_pull = self.context.socket(zmq.PULL)
        self.socket_pull.connect("inproc://queue")
        self.socket_pull.setsockopt(zmq.RCVTIMEO, self.timeout * 1000)  # 设置接收超时时间

    def __str__(self):
        return "ZeroMQLog using ZeroMQ"

    def __repr__(self):
        return f"ZeroMQLog(socket={self.socket_push})"

    def __iter__(self):
        return self

    def __next__(self):
        try:
            message = self.socket_pull.recv_json()
            if message == '>-[END]>>':
                raise StopIteration
            return TextBlock(message['block_type'], message['text'])
        except zmq.Again:  # 超时
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
                self.socket_push.send_json({"block_type": block.block_type, "text": block.text}, zmq.NOBLOCK)
                last_block_type = block.block_type

            if block.block_type in ['info', 'warn', 'text', 'tool_resp', 'tools_call']:
                self.socket_push.send_json({"block_type": block.block_type, "text": block.text}, zmq.NOBLOCK)
                if last_block_type == "chunk":
                    last_block_type = ""
                last_block_type = block.block_type
        
        if last_block_type == "chunk":
            last_block_type = ""
        
        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            block = TextBlock("info", json.dumps(final_tools_call, ensure_ascii=False))
            self.socket_push.send_json({"block_type": block.block_type, "text": block.text}, zmq.NOBLOCK)

        # 放入结束标志
        return {"output": output_text, "tools_call": final_tools_call}

    def end(self):
        self.socket_push.send_json('>-[END]>>', zmq.NOBLOCK)