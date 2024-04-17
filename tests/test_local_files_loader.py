import os
import shutil
import pytest
from unittest.mock import patch
from langchain_chinese import LocalFilesLoader
from langchain_zhipu import ChatZhipuAI

# set documents_folder to init LocalFilesLoader
target_folder = "/tmp/documents_folder"

@pytest.fixture(scope='module', autouse=True)
def prepare_data():
    os.makedirs(target_folder, exist_ok=True)

    # create some files with different extensions in the root directory
    extensions = ['txt', 'docx', 'pdf', 'jpg']
    for i, ext in enumerate(extensions):
        with open(os.path.join(target_folder, f'test{i}.{ext}'), 'w') as f:
            f.write('test')

    # create a subdirectory and some files in it
    subfolder = os.path.join(target_folder, 'include_dir')
    os.makedirs(subfolder, exist_ok=True)
    for i, ext in enumerate(extensions):
        with open(os.path.join(subfolder, f'test{i}.{ext}'), 'w') as f:
            f.write('test')

    subfolder = os.path.join(target_folder, 'exclude_dir')
    os.makedirs(subfolder, exist_ok=True)
    for i, ext in enumerate(extensions):
        with open(os.path.join(subfolder, f'test{i}.{ext}'), 'w') as f:
            f.write('test')

    yield  # this is where the testing happens

    # teardown code
    shutil.rmtree(target_folder)

def test_list_files_in_directory():
    # Test with relative path
    loader = LocalFilesLoader(documents_folder=target_folder)
    files = loader.get_files()
    assert len(files) == 6

    # Test with absolute path
    loader = LocalFilesLoader(documents_folder=os.path.abspath(target_folder))
    files = loader.get_files()
    assert len(files) == 6  # change this to the expected number of files

    # Test with environment variable
    with patch.dict(os.environ, {'LANGCHAIN_CHINESE_DOCUMENTS_FOLDER': target_folder}):
        loader = LocalFilesLoader()
        files = loader.get_files()
        assert len(files) == 6  # change this to the expected number of files

    # Test with subfolder
    loader = LocalFilesLoader(documents_folder=os.path.join(target_folder, 'include_dir'))
    files = loader.get_files()
    assert len(files) == 2  # change this to the expected number of files

    # test extensions
    loader = LocalFilesLoader(documents_folder=target_folder, extensions=['docx'])
    files = loader.get_files()
    assert len(files) == 3

    # test includes
    loader = LocalFilesLoader(
        documents_folder=target_folder,
        extensions=['docx'],
        includes=["include_dir"]
    )
    files = loader.get_files()
    assert len(files) == 1

    # test excludes
    loader = LocalFilesLoader(
        documents_folder=os.path.abspath(target_folder),
        extensions=['docx'],
        excludes=["exclude_dir"]
    )
    files = loader.get_files()
    assert len(files) == 2

def test_change_default_extensions():
    loader = LocalFilesLoader(documents_folder=target_folder, extensions=['docx'])
    files = loader.get_files()
    assert all(file.endswith('.docx') for file in files)
