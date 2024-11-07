from typing import Set, Union
import uuid
import re

from ...io import log
from ...config import get_env

class Team():
    """
    管理多个 ChatAgent 实例，以及他们之间的共享资源、事件收集。
    """
    def __init__(
        self,
        agents: Set[Union["ChatAgent"]]=None,
        default_agent: Union["ChatAgent"]=None,
        store: dict=None,
        chat_learn_folder: str=None,
        name: str=None,
        description: str=None,
        chunk_types: list=None,
        other_types: list=None,
    ):
        self.name = name or str(uuid.uuid1())
        self.description = description or ""

        self.agents = agents if agents else set()
        self.agents_thread_ids = {}
        self.default_agent = default_agent or next(iter(self.agents), None)
        self.chat_learn_folder = chat_learn_folder or get_env("ILLUFLY_CHAT_LEARN")

        self.store = store or {}
        self.last_history_id = str(uuid.uuid1())
        self.chunk_types = chunk_types or ["chunk", "tool_resp_chunk", "text", "tool_resp_text"]
        self.other_types = other_types or []

    def __repr__(self):
        return f"Team(name={self.name}, agents={self.names}, folder={self.folders})"

    @property
    def names(self):
        return [agent.name for agent in self.agents]

    @property
    def folders(self):
        return [self.chat_learn_folder]

    def create_new_history(self):
        self.last_history_id = str(uuid.uuid1())

    def __call__(self, prompt: str, **kwargs):
        """
        根据 prompt 中包含的 @agent_name 名称调用团队成员，如果未指定就调用默认成员。
        """
        handlers = kwargs.pop("handlers", [log, self.collect_event])
        names = self.get_agent_names(prompt)
        for name in names:
            prompt = re.sub(rf"(^|\s)@{name}\s", " ", prompt)
        prompt = prompt.strip()
        for agent in self.get_agents(names):
            agent(prompt, handlers=handlers, **kwargs)

    def get_agent_names(self, prompt: str):
        """
        返回agent名称列表，如果列表为空就返回self.agents中的第一个
        """
        agent_names = [agent.name for agent in self.agents if re.search(r"(^|\s)@(\w+)\s", prompt)]
        if agent_names:
            return agent_names
        else:
            return [next(iter(self.agents)).name] if self.agents else []

    def get_agents(self, names: str):
        """
        根据名称返回智能体
        """
        return [agent for agent in self.agents if agent.name in names]

    def hire(self, *agents: Union["ChatAgent"]):
        """
        雇佣一个智能体
        """
        for agent in agents:
            agent.team = self
            self.agents.add(agent)

    def fire(self, *agents: Union["ChatAgent"]):
        """
        解雇一个智能体
        """
        for agent in agents:
            agent.team = None
            self.agents.discard(agent)

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
            if self.last_history_id not in self.store:
                self.store[self.last_history_id] = {}

            calling_id = event.runnable_info["calling_id"]
            if calling_id not in self.store[self.last_history_id]:
                self.store[self.last_history_id][calling_id] = {
                    "input": "",
                    "output": "",
                    "segments": {},
                    "other_events": []
                }

            node = self.store[self.last_history_id][calling_id]
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