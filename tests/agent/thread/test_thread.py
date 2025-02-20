import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, List

from illufly.agent.thread import Thread

class Test_thread_Models:
    """Thread模型测试"""

    def test_thread_validation(self):
        """测试Thread模型验证"""
        thread = Thread(user_id="test_user")
        assert thread.user_id == "test_user"
        assert thread.thread_id is not None