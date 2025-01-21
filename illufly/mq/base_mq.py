import logging
import zmq
import zmq.asyncio
from .utils import normalize_address, cleanup_bound_socket
from ..async_utils import AsyncUtils

class BaseMQ:
    """MQ基类"""
    def __init__(self, address=None, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self._address = address
        self._context = zmq.asyncio.Context.instance()
        self._bound_socket = None
        self._connected_socket = None
        self._async_utils = AsyncUtils(self._logger)
    
    def to_binding(self):
        """初始化绑定socket"""
        pass

    def to_connecting(self):
        """初始化连接socket"""
        pass

    def cleanup(self):
        """清理资源"""
        if self._bound_socket:
            self._bound_socket.close()
            self._bound_socket = None
            self._logger.debug(f"Publisher socket closed")

    def __del__(self):
        """析构函数确保资源被清理"""
        try:
            self.cleanup()
        except Exception as e:
            if self._logger:
                self._logger.warning(f"Error during Publisher cleanup: {e}")