import pytest
import tempfile
import json
import os
import shutil
from pathlib import Path

from illufly.documents.topic import TopicManager

@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def topic_manager(temp_dir):
    """创建主题管理器实例"""
    return TopicManager(temp_dir)

@pytest.fixture
def setup_test_dirs(topic_manager):
    """设置测试目录和文件结构"""
    user_id = "test_user"
    
    # 创建主目录
    user_base = topic_manager.get_user_base(user_id)
    
    # 创建测试主题结构
    # /user_base
    # ├── topic1/
    # │   ├── subtopic1/
    # │   ├── __id_doc1__/ (文档目录，使用新命名格式)
    # │   └── __id_doc2__/ (文档目录，使用新命名格式)
    # └── topic2/
    #     └── subtopic2/
    
    # 创建主题目录
    topic1 = user_base / "topic1"
    topic1.mkdir(exist_ok=True)
    
    subtopic1 = topic1 / "subtopic1"
    subtopic1.mkdir(exist_ok=True)
    
    # 创建文档目录
    doc1_id = "doc1"
    doc1 = topic1 / f"__id_{doc1_id}__"
    doc1.mkdir(exist_ok=True)
    
    doc2_id = "doc2"
    doc2 = topic1 / f"__id_{doc2_id}__"
    doc2.mkdir(exist_ok=True)
    
    # 创建第二个主题
    topic2 = user_base / "topic2"
    topic2.mkdir(exist_ok=True)
    
    subtopic2 = topic2 / "subtopic2"
    subtopic2.mkdir(exist_ok=True)
    
    return user_id

def test_init(temp_dir):
    """测试主题管理器初始化"""
    manager = TopicManager(temp_dir)
    assert manager.base_dir == Path(temp_dir)
    assert manager.base_dir.exists()

def test_get_user_base(topic_manager):
    """测试获取用户根目录"""
    user_id = "test_user_123"
    user_base = topic_manager.get_user_base(user_id)
    
    # 检查目录是否创建
    assert user_base.exists()
    assert user_base.is_dir()
    assert user_base == topic_manager.base_dir / user_id

def test_get_topic_path(topic_manager):
    """测试获取主题路径"""
    user_id = "test_user"
    
    # 根目录
    root_path = topic_manager.get_topic_path(user_id)
    assert root_path == topic_manager.get_user_base(user_id)
    
    # 子主题路径
    subtopic_path = topic_manager.get_topic_path(user_id, "topic1/subtopic1")
    assert subtopic_path == topic_manager.get_user_base(user_id) / "topic1" / "subtopic1"

def test_is_document_dir(topic_manager, setup_test_dirs):
    """测试判断目录是否为文档目录"""
    user_id = setup_test_dirs
    
    # 文档目录（使用__id_{document_id}__命名）
    doc_dir = topic_manager.get_topic_path(user_id, "topic1/__id_doc1__")
    assert topic_manager.is_document_dir(doc_dir) is True
    
    # 普通目录（不使用__id__{document_id}__命名）
    normal_dir = topic_manager.get_topic_path(user_id, "topic1/subtopic1")
    assert topic_manager.is_document_dir(normal_dir) is False

def test_get_topic_structure(topic_manager, setup_test_dirs):
    """测试获取主题结构信息"""
    user_id = setup_test_dirs
    
    # 测试根目录结构
    root_structure = topic_manager.get_topic_structure(user_id)
    assert root_structure["user_id"] == user_id
    assert root_structure["path"] == ""
    assert set(root_structure["subtopics"]) == {"topic1", "topic2"}
    assert root_structure["document_ids"] == []
    
    # 测试子主题结构
    topic1_structure = topic_manager.get_topic_structure(user_id, "topic1")
    assert topic1_structure["user_id"] == user_id
    assert topic1_structure["path"] == "topic1"
    assert set(topic1_structure["subtopics"]) == {"subtopic1"}
    assert set(topic1_structure["document_ids"]) == {"__id_doc1__", "__id_doc2__"}

def test_list_all_topics(topic_manager, setup_test_dirs):
    """测试列出所有主题"""
    user_id = setup_test_dirs
    
    all_topics = topic_manager.list_all_topics(user_id)
    
    # 应返回4个主题（根目录、topic1、topic1/subtopic1、topic2、topic2/subtopic2）
    assert len(all_topics) == 5
    
    # 检查路径
    paths = [topic["path"] for topic in all_topics]
    assert "/" in paths  # 根目录
    assert "topic1" in paths
    assert "topic1/subtopic1" in paths
    assert "topic2" in paths
    assert "topic2/subtopic2" in paths
    
    # 检查文档计数
    topic1_info = next(t for t in all_topics if t["path"] == "topic1")
    assert topic1_info["document_count"] == 2
    assert topic1_info["subtopic_count"] == 1

def test_get_document_ids_in_topic(topic_manager, setup_test_dirs):
    """测试获取主题下的文档ID"""
    user_id = setup_test_dirs
    
    # topic1包含两个文档
    doc_ids = topic_manager.get_document_ids_in_topic(user_id, "topic1")
    assert set(doc_ids) == {"__id_doc1__", "__id_doc2__"}
    
    # 根目录不包含文档
    root_doc_ids = topic_manager.get_document_ids_in_topic(user_id)
    assert root_doc_ids == []
    
    # 子主题不包含文档
    subtopic_doc_ids = topic_manager.get_document_ids_in_topic(user_id, "topic1/subtopic1")
    assert subtopic_doc_ids == []

def test_create_topic(topic_manager):
    """测试创建主题目录"""
    user_id = "test_user"
    
    # 创建新主题
    new_topic = "new_topic/with/nested/structure"
    result = topic_manager.create_topic(user_id, new_topic)
    assert result is True
    
    # 验证目录已创建
    topic_path = topic_manager.get_topic_path(user_id, new_topic)
    assert topic_path.exists()
    assert topic_path.is_dir()
    
    # 尝试创建已存在的主题
    result2 = topic_manager.create_topic(user_id, new_topic)
    assert result2 is True  # 已存在也返回成功
    
    # 尝试创建根目录（应该返回False）
    result3 = topic_manager.create_topic(user_id, "")
    assert result3 is False

def test_delete_topic(topic_manager, setup_test_dirs):
    """测试删除主题目录"""
    user_id = setup_test_dirs
    
    # 删除不包含文档的主题
    result = topic_manager.delete_topic(user_id, "topic2/subtopic2")
    assert result is True
    
    # 验证主题已删除
    topic_path = topic_manager.get_topic_path(user_id, "topic2/subtopic2")
    assert not topic_path.exists()
    
    # 尝试删除包含文档的主题（不使用force）
    result2 = topic_manager.delete_topic(user_id, "topic1")
    assert result2 is False  # 应该失败
    assert topic_manager.get_topic_path(user_id, "topic1").exists()  # 目录仍存在
    
    # 使用force删除包含文档的主题
    result3 = topic_manager.delete_topic(user_id, "topic1", force=True)
    assert result3 is True
    assert not topic_manager.get_topic_path(user_id, "topic1").exists()  # 目录已删除
    
    # 尝试删除根目录（应该返回False）
    result4 = topic_manager.delete_topic(user_id, "")
    assert result4 is False

def test_rename_topic(topic_manager, setup_test_dirs):
    """测试重命名主题目录"""
    user_id = setup_test_dirs
    
    # 重命名主题
    old_path = "topic2/subtopic2"
    new_name = "renamed_subtopic"
    result = topic_manager.rename_topic(user_id, old_path, new_name)
    assert result is True
    
    # 验证目录已重命名
    old_topic_path = topic_manager.get_topic_path(user_id, old_path)
    assert not old_topic_path.exists()
    
    new_topic_path = topic_manager.get_topic_path(user_id, "topic2/renamed_subtopic")
    assert new_topic_path.exists()
    
    # 尝试重命名到已存在的目录
    result2 = topic_manager.rename_topic(user_id, "topic1", "topic2")
    assert result2 is False  # 应该失败
    
    # 尝试重命名根目录（应该返回False）
    result3 = topic_manager.rename_topic(user_id, "", "new_root")
    assert result3 is False

def test_move_topic(topic_manager, setup_test_dirs):
    """测试移动主题到另一个位置"""
    user_id = setup_test_dirs
    
    # 移动主题
    source_path = "topic1/subtopic1"
    target_path = "topic2"
    result = topic_manager.move_topic(user_id, source_path, target_path)
    assert result is True
    
    # 验证目录已移动
    old_path = topic_manager.get_topic_path(user_id, source_path)
    assert not old_path.exists()
    
    new_path = topic_manager.get_topic_path(user_id, "topic2/subtopic1")
    assert new_path.exists()
    
    # 移动到不存在的目录（应自动创建）
    source_path2 = "topic1/__id_doc1__"
    target_path2 = "new_target"
    result2 = topic_manager.move_topic(user_id, source_path2, target_path2)
    assert result2 is True
    
    new_path2 = topic_manager.get_topic_path(user_id, "new_target/__id_doc1__")
    assert new_path2.exists()
    
    # 创建一个与要移动的目录同名的文档目录
    topic_manager.create_topic(user_id, "topic2/__id_doc2__")
    
    # 尝试移动到已存在同名目录的位置
    result3 = topic_manager.move_topic(user_id, f"topic1/__id_doc2__", "topic2")
    assert result3 is False  # 应该失败
    
    # 尝试移动根目录（应该返回False）
    result4 = topic_manager.move_topic(user_id, "", "somewhere")
    assert result4 is False

def test_copy_topic(topic_manager, setup_test_dirs):
    """测试复制主题到另一个位置"""
    user_id = setup_test_dirs
    
    # 复制主题
    source_path = "topic1"
    target_path = "topic2"
    result = topic_manager.copy_topic(user_id, source_path, target_path)
    assert result is True
    
    # 验证原目录仍然存在
    source_dir = topic_manager.get_topic_path(user_id, source_path)
    assert source_dir.exists()
    
    # 验证目标目录已创建
    target_dir = topic_manager.get_topic_path(user_id, "topic2/topic1")
    assert target_dir.exists()
    
    # 验证子目录和文件已复制
    assert (target_dir / "subtopic1").exists()
    assert (target_dir / "__id_doc1__").exists()
    assert (target_dir / "__id_doc2__").exists()
    
    # 尝试复制到已存在同名目录的位置
    result2 = topic_manager.copy_topic(user_id, "topic1", "topic2")
    assert result2 is False  # 应该失败
    
    # 尝试复制根目录（应该返回False）
    result3 = topic_manager.copy_topic(user_id, "", "somewhere")
    assert result3 is False

def test_merge_topics(topic_manager, setup_test_dirs):
    """测试合并两个主题目录"""
    user_id = setup_test_dirs
    
    # 准备测试数据：创建新的主题和文件
    topic_manager.create_topic(user_id, "source/subtopic_a")
    topic_manager.create_topic(user_id, "target/subtopic_b")
    
    # 创建文档目录
    doc_id = "doc_source"
    doc_folder = f"__id_{doc_id}__"
    doc_path = topic_manager.get_topic_path(user_id, f"source/{doc_folder}")
    doc_path.mkdir(exist_ok=True)
    
    # 合并主题
    result = topic_manager.merge_topics(user_id, "source", "target")
    assert result is True
    
    # 验证源目录仍然存在
    source_dir = topic_manager.get_topic_path(user_id, "source")
    assert source_dir.exists()
    
    # 验证目标目录包含合并的内容
    target_dir = topic_manager.get_topic_path(user_id, "target")
    assert (target_dir / "subtopic_a").exists()  # 子主题已合并
    assert (target_dir / "subtopic_b").exists()  # 原有子主题保留
    assert (target_dir / doc_folder).exists()  # 文档已合并
    
    # 测试冲突情况
    # 在目标创建同名文档目录
    conflict_id_target = "conflict"
    conflict_folder_target = f"__id_{conflict_id_target}__"
    conflict_doc_target = topic_manager.get_topic_path(user_id, f"target/{conflict_folder_target}")
    conflict_doc_target.mkdir(exist_ok=True)
    
    # 在源创建同名文档目录
    conflict_id_source = "conflict_source"
    conflict_folder_source = f"__id_{conflict_id_source}__"
    conflict_doc_source = topic_manager.get_topic_path(user_id, f"source/{conflict_folder_target}")
    conflict_doc_source.mkdir(exist_ok=True)
    # 添加一个标记文件用于测试覆盖
    marker_file = conflict_doc_source / "marker.txt"
    with open(marker_file, "w") as f:
        f.write("source marker")
    
    # 不使用overwrite进行合并
    result2 = topic_manager.merge_topics(user_id, "source", "target", overwrite=False)
    assert result2 is True
    
    # 使用overwrite进行合并
    result3 = topic_manager.merge_topics(user_id, "source", "target", overwrite=True)
    assert result3 is True
    
    # 检查标记文件是否被覆盖
    marker_path = target_dir / conflict_folder_target / "marker.txt"
    assert marker_path.exists()
    with open(marker_path, "r") as f:
        content = f.read()
        assert content == "source marker"

def test_search_topics(topic_manager, setup_test_dirs):
    """测试搜索包含关键字的主题"""
    user_id = setup_test_dirs
    
    # 搜索 "topic1"
    results = topic_manager.search_topics(user_id, "topic1")
    assert len(results) == 2  # 应匹配 "topic1" 和 "topic1/subtopic1"
    
    # 搜索 "subtopic"
    results2 = topic_manager.search_topics(user_id, "subtopic")
    assert len(results2) == 2  # 只有两个主题包含"subtopic"
    
    # 大小写不敏感测试
    results3 = topic_manager.search_topics(user_id, "TOPIC2")
    assert len(results3) > 0
    
    # 不存在的关键字
    results4 = topic_manager.search_topics(user_id, "nonexistent")
    assert len(results4) == 0

def test_extract_document_id(topic_manager):
    """测试从文档目录名提取document_id"""
    # 有效的文档目录
    dir_path = Path("__id_test123__")
    extracted_id = topic_manager.extract_document_id(dir_path)
    assert extracted_id == "test123"
    
    # 无效的目录
    invalid_dir = Path("normal_dir")
    invalid_id = topic_manager.extract_document_id(invalid_dir)
    assert invalid_id is None

def test_get_document_folder_name(topic_manager):
    """测试生成文档目录名"""
    document_id = "test123"
    folder_name = topic_manager.get_document_folder_name(document_id)
    assert folder_name == "__id_test123__"