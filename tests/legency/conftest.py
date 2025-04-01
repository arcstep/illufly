import pytest
import logging

@pytest.fixture(autouse=True)
def setup_log(caplog):
    caplog.set_level(logging.INFO)

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "anyio: mark test as anyio test"
    )

def pytest_addoption(parser):
    """添加命令行选项"""
    parser.addoption(
        "--real",
        action="store_true",
        default=False,
        help="使用真实网络调用而不是录制的响应"
    )

@pytest.fixture
def anyio_backend():
    """强制使用 asyncio 后端"""
    return "asyncio"

@pytest.fixture
def use_real(request):
    """获取 --real 参数的值"""
    return request.config.getoption("--real")