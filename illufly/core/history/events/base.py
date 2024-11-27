from typing import List
import copy
import json
from ....io import EventBlock
from ....utils import create_id_generator

events_history_id_gen = create_id_generator()

class BaseEventsHistory():
    def __init__(
        self,
        store: dict=None,
        chunk_types: list=None,
        other_types: list=None,
    ):
        # 构建实例后由 Runnable 赋值
        self.agent_name = None

        self.store = store or {}
        self.chunk_types = chunk_types or ["chunk", "tool_resp_chunk", "text", "tool_resp_text"]

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

    def get_event_type(self, block: EventBlock):
        event_type = "log"
        is_self_generated = self.agent_name == block.runnable_info.get("name", None)

        # input
        if block.block_type == "user" and is_self_generated:
            event_type = "input"
        elif block.block_type == "final_text" and is_self_generated:
            event_type = "output"
        elif block.block_type in ["tools_call_final", "tool_resp_chunk", "tool_resp_text", "tool_resp_final_text"]:
            event_type = "tools"
        else:
            event_type = "log"

        return event_type

    def get_event_data(self, block: EventBlock):
        return json.dumps({
            "content": block.text,
            "block_type": block.block_type,
            "content_id": block.content_id,
            "created_at": block.created_at.isoformat(),
            "thread_id": block.runnable_info.get("thread_id", None),
            "calling_id": block.runnable_info.get("calling_id", None),
            "agent_name": block.runnable_info.get("name", None),
            "model_name": block.runnable_info.get("model_name", None),
        }, ensure_ascii=False)
    
    @property
    def event_stream(self):
        """
        生成适合于 Web 处理的 SSE 事件流格式的数据。
        如果使用 FastAPI，则可以使用 `event_stream` 作为 `EventSourceResponse` 的生成器。
        """
        def _event_stream(block, verbose: bool=False, **kwargs):
            if isinstance(block, EventBlock):
                return {
                    "id": block.id,
                    "event": self.get_event_type(block),
                    "data": self.get_event_data(block)
                }
            else:
                return {"data": ""}

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
                    "id": event.id,
                    "event_type": self.get_event_type(event),
                    "data": self.get_event_data(event),
                }

        return _collect
