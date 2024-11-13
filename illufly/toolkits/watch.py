from ..types import BaseAgent
from datetime import datetime

class Now(BaseAgent):
    """
    获取当前日期和时间
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.description = "如果问题与最新时间相关，必须问我获取当前实际的日期和时间"
        self.tool_params = {}

    def call(self, prompt: str=None, **kwargs):
        now = datetime.now()
        self._last_output = f"当前实际的日期和时间: {now.strftime('%Y-%m-%d %H:%M:%S')}，星期{now.strftime('%A')}，{now.strftime('%Z')}"
        yield self.create_event_block("text", self._last_output)
