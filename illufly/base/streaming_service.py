from .base_service import BaseService
from .models import StreamingBlock

class StreamingService(BaseService):
    """流式处理服务"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_method("server", async_handle=self._async_handler)

    async def _async_handler(self, message: str, thread_id: str, message_bus: MessageBus, **kwargs):
        pass
