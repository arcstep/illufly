import json
import os
import requests
import uuid

from ...types import BaseAgent
from ...utils import raise_invalid_params
from ..http import (
    EventBlock,
    send_request,
    ZHIPUAI_API_TOOLS_BASE_URL,
)

class WebSearch(BaseAgent):
    """
    [API](https://open.bigmodel.cn/dev/api/search-tool/web-search-pro)
    """
    @classmethod
    def allowed_params(cls):
        return {
            "model": "模型名称",
            "api_key": "API_KEY",
            **BaseAgent.allowed_params()
        }

    def __init__(self, tool: str=None, api_key: str=None, **kwargs):
        raise_invalid_params(kwargs, self.__class__.allowed_params())

        tools_params = kwargs.pop("tool_params", {"prompt": "请给出互联网搜索的内容关键字"})
        description = kwargs.pop("description", "搜索互联网内容")

        super().__init__(
            threads_group="WebSearch",
            tool_params=tools_params,
            description=description,
            **kwargs
        )

        self.tool = tool or "web-search-pro"
        self.api_key = api_key or os.getenv("ZHIPUAI_API_KEY")

    def call(
        self, 
        prompt: str=None,
        **kwargs
    ):
        self._last_output = ""

        data = {
            "request_id": str(uuid.uuid1()),
            "tool": self.tool,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}]
        }

        resp = requests.post(
            ZHIPUAI_API_TOOLS_BASE_URL,
            json=data,
            headers={'Authorization': self.api_key},
            timeout=300
        )

        resp_content = resp.content.decode()
        for line in resp_content.splitlines():
            if line.startswith("data: "):
                data = line[len("data: "):]
                if data == "[DONE]":
                    break
                content = json.loads(data)
                if content.get("model", None) == "web-search-pro":
                    choices = content.get("choices", [])
                    for choice in choices:
                        for item in choice.get("delta", {}).get("tool_calls", []):
                            indent_type = item.get("type", None)
                            if indent_type == "search_intent":
                                yield self.create_event_block("WEB_SEARCH_INTENT", item.get("search_intent", ""))
                            elif indent_type == "search_result":
                                output = item.get("search_result", "")
                                if output:
                                    text = "\n\n".join([
                                        f'## [{r.get("title", "No Title")}]({r.get("link", "#")})\n{r.get("content", "No Content")}'
                                        for r
                                        in output
                                    ])
                                    yield self.create_event_block("TEXT", text)
                                    self._last_output += text
