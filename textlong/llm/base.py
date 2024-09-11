from abc import ABC, abstractmethod
from typing import Union, List, Dict, Any
from ..base import CallBase
from ..utils import merge_blocks_by_index
from ..io import TextBlock
import json

class ChatBase(CallBase):
    def __init__(self, memory: List[Dict[str, Any]]=None):
        self.memory = memory or []
        super().__init__(threads_group="base_llm")

    def add_prompt_to_memory(self, prompt: Union[str, List[dict]]):
        if isinstance(prompt, str):
            new_memory = {"role": "user", "content": prompt}
        else:
            new_memory = prompt[-1]
        self.memory.append(new_memory)
    
    def add_response_to_memory(self, response: Union[str, List[dict]]):
        if isinstance(response, str):
            new_memory = {"role": "assistant", "content": response}
        else:
            new_memory = response[-1]
        self.memory.append(new_memory)

    def call(self, prompt: Union[str, List[dict]], *args, **kwargs):
        self.add_prompt_to_memory(prompt)

        output_text = ""
        tools_call = []
        for block in self.generate(prompt, *args, **kwargs):
            yield block
            if block.block_type == "chunk":
                output_text += block.content
            if block.block_type == "tools_call_chunk":
                tools_call.append(json.loads(block.text))

        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            content = json.dumps(final_tools_call, ensure_ascii=False)
            self.add_response_to_memory(content)
            yield TextBlock("tools_call_final", content)

        if output_text:
            self.add_response_to_memory(output_text)
            yield TextBlock("text_final", output_text)

    @abstractmethod
    def generate(self, prompt: Union[str, List[dict]], *args, **kwargs):
        pass