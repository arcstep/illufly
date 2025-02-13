class ChatsManager:
    """聊天管理器"""

    def __init__(self, db: IndexedRocksDB):
        self.db = db

    def create_chat(self, user_id: str, name: str) -> Result[Chat]:
        """创建聊天"""
        pass

    def chat(self, user_id: str, chat_id: str, message: str) -> Result[ChatMessage]:
        """聊天"""
        pass

    def get_chat(self, user_id: str, chat_id: str) -> Result[Chat]:
        """获取聊天"""
        pass

    def get_history(self, user_id: str, chat_id: str) -> Result[List[ChatMessage]]:
        """获取聊天历史"""
        pass

    def delete_chat(self, user_id: str, chat_id: str) -> Result[None]:
        """删除聊天"""
        pass
