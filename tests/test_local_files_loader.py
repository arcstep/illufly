import os
import shutil
import pytest
from langchain_chinese.document_loaders import LocalFilesLoader

# set documents_folder to init LocalFilesLoader
target_folder = "/tmp/documents_folder"

@pytest.fixture(scope='module', autouse=True)
def prepare_data():
    os.makedirs(target_folder, exist_ok=True)

    # create some files with different extensions
    extensions = ['txt', 'docx', 'pdf', 'jpg']
    for i, ext in enumerate(extensions):
        with open(os.path.join(target_folder, f'test{i}.{ext}'), 'w') as f:
            f.write('test')

    # create a subdirectory
    os.makedirs(os.path.join(target_folder, 'subdirectory'), exist_ok=True)

    # create some files in the subdirectory
    for i, ext in enumerate(extensions):
        with open(os.path.join(target_folder, 'subdirectory', f'test{i}.{ext}'), 'w') as f:
            f.write('test')

    # create some files to include
    for i in range(3):
        with open(os.path.join(target_folder, f'include_test{i}.txt'), 'w') as f:
            f.write('test')

    # create some files to exclude
    for i in range(3):
        with open(os.path.join(target_folder, f'exclude_test{i}.txt'), 'w') as f:
            f.write('test')

    yield  # this is where the testing happens

    # teardown code
    shutil.rmtree(target_folder)

def test_list_files_in_directory():
    loader = LocalFilesLoader(documents_folder = target_folder)
    files = loader.get_files()
    # 检查是否列出了所有文件
    assert len(files) == 4

def test_list_files_in_subdirectory():
    loader = LocalFilesLoader(documents_folder = target_folder)
    loader.includes = ['subdirectory']
    files = loader.get_files()
    # 检查是否只列出了子目录中的文件
    assert len(files) == 2

def test_change_default_extensions():
    loader = LocalFilesLoader(documents_folder = target_folder)
    loader.extensions = ['txt']
    files = loader.get_files()
    # 检查是否只列出了 .txt 文件
    assert all(file.endswith('.txt') for file in files)

def test_change_includes():
    loader = LocalFilesLoader(documents_folder = target_folder)
    loader.includes = ['include']
    files = loader.get_files()
    # 检查是否只列出了 includes 中指定的文件
    assert all('include' in file for file in files)

def test_change_excludes():
    loader = LocalFilesLoader(documents_folder = target_folder)
    loader.excludes = ['exclude']
    files = loader.get_files()
    # 检查是否没有列出 excludes 中指定的文件
    assert all('exclude' not in file for file in files)