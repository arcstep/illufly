from typing import Union, List, AsyncGenerator, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import threading
import zmq.asyncio
import uuid
import json
from enum import Enum

from ...types import EventBlock
from ..base import BaseStreamingService

class FakeChat(BaseStreamingService):
    def __init__(
        self, 
        response: Union[str, List[str]]=None, 
        sleep: float=None,
        **kwargs
    ):
        self.sleep = sleep if sleep is not None else 0.2
        self.response = response if isinstance(response, list) else ([response] if response else None)
        self.current_response_index = 0
        
        self.logger.info(
            f"Initializing FakeChat with "
            f"response_length: {len(response) if response else 'default'}, "
            f"sleep: {sleep}s"
        )
        
        super().__init__(**kwargs)

    async def process_request(self, prompt: str, **kwargs):
        self.logger.debug(f"Processing prompt: {prompt[:50]}...")
        
        yield EventBlock(block_type="info", content=f'I am FakeLLM')
        
        if self.response:
            resp = self.response[self.current_response_index]
            self.logger.debug(
                f"Using response {self.current_response_index + 1}/{len(self.response)}: "
                f"{resp[:50]}..."
            )
            self.current_response_index = (self.current_response_index + 1) % len(self.response)
        else:
            resp = f"Reply >> {prompt}"
            self.logger.debug(f"Using default response format")

        chunk_count = 0
        for content in resp:
            chunk_count += 1
            await asyncio.sleep(self.sleep)
            yield EventBlock(block_type="chunk", content=content)
        
        self.logger.debug(f"Completed streaming {chunk_count} chunks")
        yield EventBlock(block_type="end", content="")
