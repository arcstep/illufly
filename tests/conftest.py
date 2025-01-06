import pytest
import logging

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "anyio: mark test as anyio test"
    )

@pytest.fixture
def anyio_backend():
    """强制使用 asyncio 后端"""
    return "asyncio"