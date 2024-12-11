import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Callable
from illufly.fastapi.common.file_storage import FileStorage
from tests.fixtures.data_types import TestData

@pytest.fixture
def test_data_factory():
    def create_test_data(id: str = "1", name: str = "张三", age: int = 25) -> TestData:
        return TestData(id=id, name=name, age=age)
    return create_test_data

@pytest.fixture
def storage_factory():
    temp_dirs = []
    
    def create_storage(use_id_subdirs: bool = False) -> FileStorage[TestData]:
        temp_dir = tempfile.mkdtemp()
        temp_dirs.append(temp_dir)
        
        def serializer(data: TestData) -> Dict:
            return data.to_dict()
            
        def deserializer(data: Dict) -> TestData:
            return TestData.from_dict(data)
            
        return FileStorage(
            data_dir=temp_dir,
            filename="test.json",
            serializer=serializer,
            deserializer=deserializer,
            use_id_subdirs=use_id_subdirs
        )
    
    yield create_storage
    
    # 清理临时目录
    for temp_dir in temp_dirs:
        shutil.rmtree(temp_dir)