from dotenv import find_dotenv
import os
import pytest
from langchain_chinese import BaseProject, WritingChain
from langchain_community.chat_models.fake import FakeListChatModel

def test_validate_base_environment():
    # 测试 PROJECT_FOLDER 环境变量为相对路径的情况
    os.environ["PROJECT_FOLDER"] = "relative/path/to/project"
    instance = BaseProject()
    assert instance.project_folder == os.path.join(os.path.dirname(find_dotenv()), "relative/path/to/project")

    # 测试 PROJECT_FOLDER 环境变量为绝对路径的情况
    os.environ["PROJECT_FOLDER"] = "/absolute/path/to/project"
    instance = BaseProject()
    assert instance.project_folder == "/absolute/path/to/project"

    # 测试 PROJECT_FOLDER 环境变量为 None 的情况
    os.environ.pop("PROJECT_FOLDER", None)
    with pytest.raises(ValueError):
        instance = BaseProject()

def test_validate_writing_environment():
    fake_llm = FakeListChatModel(responses=[])
    # 设置环境变量
    os.environ["PROJECT_FOLDER"] = "/absolute/path/to/project"
    os.environ["OUTPUT_FILENAME"] = "test.md"

    # 测试 output_dir 为 None 的情况
    instance = WritingChain(llm=fake_llm)
    assert instance.output_dir == "/absolute/path/to/project"

    # 测试 output_dir 为相对路径的情况
    instance = WritingChain(llm=fake_llm, output_dir="relative/path")
    assert instance.output_dir == "/absolute/path/to/project/relative/path"

    # 测试 output_dir 为绝对路径的情况
    instance = WritingChain(llm=fake_llm, output_dir="/absolute/path/to/output")
    assert instance.output_dir == "/absolute/path/to/output"
