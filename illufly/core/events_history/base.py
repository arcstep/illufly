from typing import List
import copy

from ...io import EventBlock
from ...utils import create_id_generator

events_history_id_gen = create_id_generator()

class BaseEventsHistory():
    def __init__(
        self,
        store: dict=None,
        chunk_types: list=None,
        other_types: list=None,
    ):
        self.store = store or {}
        self.chunk_types = chunk_types or ["chunk", "tool_resp_chunk", "text", "tool_resp_text"]
        self.other_types = other_types or ["warn", "error", "info"]

        self.create_new_history()

    def list_events_histories(self):
        """列举所有历史事件"""
        return sorted(self.store.keys())

    @property
    def last_history_id(self):
        all_events_history_ids = self.list_events_histories()
        return all_events_history_ids[-1] if all_events_history_ids else None

    def last_events_history_id_count(self):
        """获取最近一轮对话的历史事件 ID"""
        all_events_history_ids = self.list_events_histories()
        if all_events_history_ids:
            ids = all_events_history_ids[-1].split("-")
            return int(ids[-1]) + 1
        else:
            return 0

    def save_events_history(self, events_history_id: str, events_history: List[dict]):
        """根据 events_history_id 保存历史事件"""
        self.store[events_history_id] = copy.deepcopy(events_history)

    def load_events_history(self, events_history_id: str=None):
        """根据 events_history_id 加载历史事件"""
        _events_history_id = events_history_id or self.last_history_id
        if isinstance(events_history_id, str):
            return _events_history_id, self.store.get(events_history_id, {})
        elif isinstance(events_history_id, int):
            all_events_history_ids = self.list_events_histories()
            if all_events_history_ids:
                _events_history_id = all_events_history_ids[events_history_id]
                return _events_history_id, self.store.get(_events_history_id, {})

        return _events_history_id, {}

    def create_new_history(self):
        last_history_id = next(events_history_id_gen)
        self.store[last_history_id] = {
            "threads": set({}),
            "callings": {}
        }

    @property
    def event_stream(self):
        """
        生成适合于 Web 处理的 SSE 事件流格式的数据。
        如果使用 FastAPI，则可以使用 `event_stream` 作为 `EventSourceResponse` 的生成器。
        """
        valid_block_types = self.chunk_types + self.other_types
        def _event_stream(block, verbose: bool=False, **kwargs):
            if isinstance(block, EventBlock) and block.block_type in valid_block_types:
                return {
                    "event": block.block_type,
                    "id": block.id,
                    "data": {
                        "content": block.text,
                        "content_id": block.content_id,
                        "thread_id": block.runnable_info.get("thread_id", None),
                        "calling_id": block.runnable_info.get("calling_id", None),
                        "agent_name": block.runnable_info.get("name", None),
                        "model_name": block.runnable_info.get("model_name", None),
                        "created_at": block.created_at.isoformat(),
                    }
                }
            else:
                return {}

        return _event_stream

    @property
    def collect_event(self):
        """
        收集事件到 store 中。

        每个 EventBlock 都包含 runnable_info 属性，其中包含 thread_id 和 calling_id。
        只有最初发起调用的 Runnable 才创建为一个 calling_id，在嵌套调用时，需要将 calling_id 传递给被调用的 Runnable。

        事件流的层次结构分为：
        - history_id 标记一个完整的对话流历史
        - calling_id 标记一次调用
        - agent_name 标记一次调用中，由哪个智能体发起
        - thread_id 如果智能体包含连续记忆，则标记连续记忆的 thread_id
        - segments 将 chunk 类事件收集到一起，形成完整段落
        """
        def _collect(event, **kwargs):
            last_history_id = self.last_history_id

            if event.runnable_info.get("thread_id", None):
                thread = (
                    event.runnable_info["name"],
                    event.runnable_info["thread_id"],
                )
                self.store[last_history_id]["threads"].add(thread)

            calling_id = event.runnable_info["calling_id"]
            if calling_id not in self.store[last_history_id]["callings"]:
                self.store[last_history_id]["callings"][calling_id] = {
                    "agent_name": event.runnable_info["name"],
                    "input": "",
                    "output": "",
                    "segments": {},
                    "other_events": []
                }

            node = self.store[last_history_id]["callings"][calling_id]

            if event.block_type == "user":
                node["input"] = event.text
            elif event.block_type in self.chunk_types:
                node["segments"][event.content_id] = node["segments"].get(event.content_id, "") + event.text
            elif event.block_type == "final_text":
                node["output"] = event.text
            elif event.block_type in self.other_types or self.other_types == "__all__":
                node["other_events"].append(event.json)
            else:
                pass

        return _collect
