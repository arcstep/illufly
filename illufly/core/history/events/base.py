from typing import List, Union
import copy
import json
from ....io import EventBlock
from ....utils import create_id_generator

events_history_id_gen = create_id_generator()

class BaseEventsHistory():
    def __init__(
        self,
        store: dict=None,
        ignore_types: list=None,
    ):
        # 构建实例后由 Runnable 赋值
        self.agent_name = None

        self.store = store or {}
        self.ignore_types = ignore_types or ["final_text", "response", "human", "new_line", "runnable"]

        self.events_history_id, _ = self.load_events_history()
        if self.events_history_id is None:
            self.events_history_id = self.create_new_history()

    def list_events_histories(self):
        """列举所有历史事件"""
        return sorted(self.store.keys())

    @property
    def last_history_id(self):
        all_events_history_ids = self.list_events_histories()
        return all_events_history_ids[-1] if all_events_history_ids else None

    def save_events_history(self):
        """根据 events_history_id 保存历史事件"""
        pass

    def load_events_history(self, events_history_id: Union[str, int]=None):
        """根据 events_history_id 加载历史事件"""
        if events_history_id is None:
            _events_history_id = self.last_history_id
        else:
            _events_history_id = events_history_id

        self.events_history_id = _events_history_id

        if isinstance(_events_history_id, str):
            return _events_history_id, self.store.get(_events_history_id, {})
        elif isinstance(_events_history_id, int):
            all_events_history_ids = self.list_events_histories()
            if all_events_history_ids:
                _events_history_id = all_events_history_ids[events_history_id]
                return _events_history_id, self.store.get(_events_history_id, {})

        return _events_history_id, {}

    def create_new_history(self):
        history_id = next(events_history_id_gen)
        self.events_history_id = history_id

        self.store[history_id] = {
            "agents": {},
            "callings": {}
        }
        return history_id

    def _get_event_data(self, block: EventBlock):
        return json.dumps({
            "block_id": block.id,
            "block_type": block.block_type,
            "content": block.text,
            "content_id": block.content_id,
            "created_at": block.created_at.isoformat(),
            "thread_id": block.runnable_info.get("thread_id", None),
            "calling_id": block.runnable_info.get("calling_id", None),
            "agent_name": block.runnable_info.get("name", None),
            "model_name": block.runnable_info.get("model_name", None),
        }, ensure_ascii=False)

    def _get_event(self, block: EventBlock):
        return {
            "id": block.id,
            "event": "message",
            "data": self._get_event_data(block)
        }

    @property
    def event_stream(self):
        """
        生成适合于 Web 处理的 SSE 事件流格式的数据。
        如果使用 FastAPI，则可以使用 `event_stream` 作为 `EventSourceResponse` 的生成器。
        """
        def _event_stream(block, verbose: bool=False, **kwargs):
            if isinstance(block, EventBlock):
                if block.block_type in self.ignore_types:
                    return None
                return self._get_event(block)
            else:
                return str(block)

        return _event_stream

    def collect_event(self, block: EventBlock):
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
        history_id = self.events_history_id

        agent_name = block.runnable_info.get("name", None)
        if agent_name and not self.store[history_id]["agents"]:
            self.store[history_id]["agents"][agent_name] = {}

        thread_id = block.runnable_info.get("thread_id", None)
        if thread_id:
            self.store[history_id]["agents"][agent_name]["thread_id"] = thread_id

        calling_id = block.runnable_info["calling_id"]
        if calling_id not in self.store[history_id]["callings"]:
            self.store[history_id]["callings"][calling_id] = []

        event = self._get_event(block)
        self.store[history_id]["callings"][calling_id].append(event)
