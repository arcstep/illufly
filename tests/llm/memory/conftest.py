import pytest
import tempfile
import shutil

from illufly.io.rocksdict import IndexedRocksDB
from illufly.llm.memory.L0_QA import QA, Thread

@pytest.fixture
def db_path():
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)

@pytest.fixture
def db(db_path):
    db = IndexedRocksDB(db_path)
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def user_id():
    return "test_user"

@pytest.fixture
def thread_id():
    thread = Thread(user_id="test_user", thread_id="test_thread")
    return thread.thread_id