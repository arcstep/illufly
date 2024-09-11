import json
import asyncio
from typing import Any, Dict, List, Union
from ..io import merge_blocks_by_index, create_chk_block, TextBlock

class BaseReasoning:
    def __init__(self, model: str):
        self.model = model

    def _process_llm_result(
        self,
        llm_result: List[Union[TextBlock, str]],
        short_term_memory: List[Dict[str, Any]],
        long_term_memory: List[Dict[str, Any]],
        toolkits: List[Any]
    ):
        output_text = ""
        tools_call = []

        for block in (llm_result or []):
            yield block
            if isinstance(block, TextBlock):
                if block.block_type in ['text', 'chunk', 'front_matter']:
                    output_text += block.text
                
                if block.block_type in ['tools_call_chunk']:
                    tools_call.append(json.loads(block.text))
            else:
                output_text += block

        final_tools_call = merge_blocks_by_index(tools_call)
        if final_tools_call:
            yield TextBlock("tools_call_final", json.dumps(final_tools_call, ensure_ascii=False))
            for index, tool in final_tools_call.items():
                for struct_tool in toolkits:
                    if tool['function']['name'] == struct_tool.name:
                        args = json.loads(tool['function']['arguments'])
                        tool_resp = ""

                        tool_func_result = struct_tool.func(**args)
                        for x in tool_func_result:
                            if isinstance(x, TextBlock):
                                if x.block_type == "tool_resp_final":
                                    tool_resp = x.text
                                yield x
                            else:
                                tool_resp += x
                                yield TextBlock("tool_resp_chunk", x)
                        tool_info = [
                            {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [tool]
                            },
                            {
                                "role": "tool",
                                "name": tool['function']['name'],
                                "content": tool_resp
                            }
                        ]
                        short_term_memory.extend(tool_info)
                        long_term_memory.extend(tool_info)
                        yield True, output_text
                        return
        else:
            long_term_memory.extend([{
                'role': 'assistant',
                'content': output_text
            }])
            short_term_memory.extend([{
                'role': 'assistant',
                'content': output_text
            }])
            yield create_chk_block(output_text)
        
        yield False, output_text

    def call(self, llm, long_term_memory, short_term_memory, toolkits, tools, **model_kwargs):
        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False
            llm_result = llm(short_term_memory, **model_kwargs)
            generator = self._process_llm_result(llm_result, short_term_memory, long_term_memory, toolkits)
            for item in generator:
                if isinstance(item, tuple):
                    to_continue_call_llm, _ = item
                else:
                    yield item

    async def a_call(self, llm, long_term_memory, short_term_memory, toolkits, **model_kwargs):
        to_continue_call_llm = True
        while to_continue_call_llm:
            to_continue_call_llm = False
            if asyncio.iscoroutinefunction(llm):
                llm_result = await llm(short_term_memory, **model_kwargs)
            else:
                llm_result = await asyncio.to_thread(llm, short_term_memory, **model_kwargs)
            generator = self._process_llm_result(llm_result, short_term_memory, long_term_memory, toolkits)
            async for item in generator:
                if isinstance(item, tuple):
                    to_continue_call_llm, _ = item
                else:
                    yield item

