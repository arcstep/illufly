import json
from typing import AsyncIterable, Union
import logging
import asyncio

from .block import EventBlock

def create_collector(store: dict):
    def collect_event(event, **kwargs):
        thread_id = event.runnable_info.get("thread_id", "__default__")
        calling_id = event.runnable_info["calling_id"]
        chunk_types = ["chunk", "tool_resp_chunk", "text", "tool_resp_text"]
        if thread_id not in store:
            store[thread_id] = {}
        if calling_id not in store[thread_id]:
            store[thread_id][calling_id] = {
                "input": "",
                "output": "",
                "segments": {},
                "other_events": []
            }
        node = store[thread_id][calling_id]
        if event.block_type == "user":
            node["input"] = event.text
        elif event.block_type in chunk_types:
            node["segments"][event.content_id] = node["segments"].get(event.content_id, "") + event.text
        elif event.block_type == "final_text":
            node["output"] = event.text
        else:
            # node["other_events"].append(event.json)
            pass

    return collect_event
