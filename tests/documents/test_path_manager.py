import os
import pytest
from pathlib import Path
from illufly.documents.path_manager import PathManager

class TestPathManager:
    @pytest.fixture
    def base_path_manager(self, tmpdir):
        """创建基本的路径管理器实例"""
        return PathManager(str(tmpdir))
    
    @pytest.fixture
    def setup_user_structure(self, base_path_manager):
        """设置基本的用户目录结构"""
        user_id = "test_user"
        # 创建一些测试目录和文件
        base_path_manager.create_topic_dir(user_id, "topic1")
        base_path_manager.create_topic_dir(user_id, "topic1/subtopic1")
        base_path_manager.create_topic_dir(user_id, "topic2")
        
        # 创建一些测试文档
        user_base = base_path_manager.get_user_base(user_id)
        (user_base / "__id_doc1__.md").write_text("测试文档1")
        (user_base / "topic1" / "__id_doc2__.md").write_text("测试文档2")
        (user_base / "topic1/subtopic1" / "__id_doc3__.md").write_text("测试文档3")
        (user_base / "topic2" / "__id_doc4__.md").write_text("测试文档4")
        
        return user_id
    
    # ==== 基础路径操作测试 ====
    def test_get_user_base(self, base_path_manager, tmpdir):
        """测试获取用户根目录"""
        user_id = "test_user"
        user_base = base_path_manager.get_user_base(user_id)
        
        assert user_base == Path(tmpdir) / user_id
        assert user_base.exists()
        assert user_base.is_dir()
    
    def test_get_topic_path(self, base_path_manager, setup_user_structure):
        """测试获取主题路径"""
        user_id = setup_user_structure
        
        # 测试根路径
        root_path = base_path_manager.get_topic_path(user_id)
        assert root_path == base_path_manager.get_user_base(user_id)
        
        # 测试子路径
        topic_path = base_path_manager.get_topic_path(user_id, "topic1")
        assert topic_path == base_path_manager.get_user_base(user_id) / "topic1"
        assert topic_path.exists()
        assert topic_path.is_dir()
        
        # 测试嵌套路径
        subtopic_path = base_path_manager.get_topic_path(user_id, "topic1/subtopic1")
        assert subtopic_path == base_path_manager.get_user_base(user_id) / "topic1" / "subtopic1"
        assert subtopic_path.exists()
        assert subtopic_path.is_dir()
    
    # ==== 文件识别与命名测试 ====
    def test_is_document_file(self, base_path_manager, setup_user_structure):
        """测试文档文件识别"""
        user_id = setup_user_structure
        user_base = base_path_manager.get_user_base(user_id)
        
        # 有效文档
        doc_file = user_base / "__id_doc1__.md"
        assert base_path_manager.is_document_file(doc_file)
        
        # 非文档文件
        non_doc_file = user_base / "regular_file.txt"
        non_doc_file.write_text("普通文件")
        assert not base_path_manager.is_document_file(non_doc_file)
        
        # 命名不符合规则的文件
        wrong_name_file = user_base / "_doc1__.md"
        wrong_name_file.write_text("命名错误的文件")
        assert not base_path_manager.is_document_file(wrong_name_file)
    
    def test_extract_document_id(self, base_path_manager):
        """测试从文件名提取文档ID"""
        # 标准文档文件
        assert base_path_manager.extract_document_id("__id_doc123__.md") == "doc123"
        assert base_path_manager.extract_document_id(Path("__id_abc123__.md")) == "abc123"
        
        # 非标准格式
        assert base_path_manager.extract_document_id("regular_file.txt") is None
        assert base_path_manager.extract_document_id("__id_file_without_end.txt") is None
    
    def test_get_document_file_name(self, base_path_manager):
        """测试根据ID生成文档文件名"""
        assert base_path_manager.get_document_file_name("doc123") == "__id_doc123__.md"
        assert base_path_manager.get_document_file_name("abc") == "__id_abc__.md"
    
    # ==== 路径结构处理测试 ====
    def test_parse_path_structure(self, base_path_manager):
        """测试解析路径结构"""
        # 空路径
        result = base_path_manager.parse_path_structure("")
        assert result["topics"] == []
        assert result["document_id"] is None
        
        # 只有主题
        result = base_path_manager.parse_path_structure("topic1/subtopic1")
        assert result["topics"] == ["topic1", "subtopic1"]
        assert result["document_id"] is None
        
        # 带有文档ID
        result = base_path_manager.parse_path_structure("topic1/subtopic1/__id_doc123__.md")
        assert result["topics"] == ["topic1", "subtopic1"]
        assert result["document_id"] == "doc123"
        
        # 多斜杠路径
        result = base_path_manager.parse_path_structure("//topic1//subtopic1//")
        assert result["topics"] == ["topic1", "subtopic1"]
        assert result["document_id"] is None
    
    def test_create_path_from_structure(self, base_path_manager):
        """测试从结构创建路径"""
        # 只有主题
        assert base_path_manager.create_path_from_structure(["topic1", "subtopic1"]) == "topic1/subtopic1"
        
        # 主题和文档ID
        path = base_path_manager.create_path_from_structure(["topic1", "subtopic1"], "doc123")
        assert path == "topic1/subtopic1/__id_doc123__.md"
        
        # 空主题列表，只有文档
        assert base_path_manager.create_path_from_structure([], "doc123") == "__id_doc123__.md"
        
        # 空主题列表，无文档
        assert base_path_manager.create_path_from_structure([]) == ""
    
    def test_get_topic_path_text(self, base_path_manager):
        """测试获取主题可读文本表示"""
        assert base_path_manager.get_topic_path_text("topic1/subtopic1") == "topic1/subtopic1"
        assert base_path_manager.get_topic_path_text("topic1/subtopic1/__id_doc123__.md") == "topic1/subtopic1"
        assert base_path_manager.get_topic_path_text("") == ""
    
    # ==== 主题结构操作测试 ====
    def test_get_physical_document_ids(self, base_path_manager, setup_user_structure):
        """测试获取主题下的文档ID"""
        user_id = setup_user_structure
        
        # 根目录
        root_docs = base_path_manager.get_physical_document_ids(user_id)
        assert "doc1" in root_docs
        assert len(root_docs) == 1
        
        # 子目录
        topic1_docs = base_path_manager.get_physical_document_ids(user_id, "topic1")
        assert "doc2" in topic1_docs
        assert len(topic1_docs) == 1
        
        # 嵌套目录
        subtopic_docs = base_path_manager.get_physical_document_ids(user_id, "topic1/subtopic1")
        assert "doc3" in subtopic_docs
        assert len(subtopic_docs) == 1
    
    def test_get_topic_structure(self, base_path_manager, setup_user_structure):
        """测试获取主题结构信息"""
        user_id = setup_user_structure
        
        # 根目录结构
        root_structure = base_path_manager.get_topic_structure(user_id)
        assert root_structure["user_id"] == user_id
        assert root_structure["path"] == ""
        assert "doc1" in root_structure["document_ids"]
        assert "topic1" in root_structure["subtopics"]
        assert "topic2" in root_structure["subtopics"]
        
        # 子目录结构
        topic1_structure = base_path_manager.get_topic_structure(user_id, "topic1")
        assert topic1_structure["user_id"] == user_id
        assert topic1_structure["path"] == "topic1"
        assert "doc2" in topic1_structure["document_ids"]
        assert "subtopic1" in topic1_structure["subtopics"]
    
    def test_get_all_topic_document_ids(self, base_path_manager, setup_user_structure):
        """测试获取所有文档ID（包括子主题）"""
        user_id = setup_user_structure
        
        # 非递归模式
        non_recursive_docs = base_path_manager.get_all_topic_document_ids(user_id, "topic1", recursive=False)
        assert "doc2" in non_recursive_docs
        assert "doc3" not in non_recursive_docs
        assert len(non_recursive_docs) == 1
        
        # 递归模式
        recursive_docs = base_path_manager.get_all_topic_document_ids(user_id, "topic1", recursive=True)
        assert "doc2" in recursive_docs
        assert "doc3" in recursive_docs
        assert len(recursive_docs) == 2
        
        # 整个用户目录
        all_docs = base_path_manager.get_all_topic_document_ids(user_id, recursive=True)
        assert len(all_docs) == 4
        assert set(all_docs) == {"doc1", "doc2", "doc3", "doc4"}
    
    # ==== 主题目录操作测试 ====
    def test_create_topic_dir(self, base_path_manager):
        """测试创建主题目录"""
        user_id = "test_user_create"
        
        # 创建新目录
        assert base_path_manager.create_topic_dir(user_id, "new_topic")
        new_topic_path = base_path_manager.get_topic_path(user_id, "new_topic")
        assert new_topic_path.exists()
        assert new_topic_path.is_dir()
        
        # 创建嵌套目录
        assert base_path_manager.create_topic_dir(user_id, "new_topic/nested")
        nested_path = base_path_manager.get_topic_path(user_id, "new_topic/nested")
        assert nested_path.exists()
        assert nested_path.is_dir()
        
        # 尝试创建已存在的目录
        assert base_path_manager.create_topic_dir(user_id, "new_topic")
        
        # 尝试创建根目录
        assert not base_path_manager.create_topic_dir(user_id, "")
    
    def test_delete_topic_dir(self, base_path_manager):
        """测试删除主题目录"""
        user_id = "test_user_delete"
        
        # 创建测试目录
        base_path_manager.create_topic_dir(user_id, "topic_to_delete")
        topic_path = base_path_manager.get_topic_path(user_id, "topic_to_delete")
        assert topic_path.exists()
        
        # 删除目录
        assert base_path_manager.delete_topic_dir(user_id, "topic_to_delete")
        assert not topic_path.exists()
        
        # 尝试删除不存在的目录
        assert base_path_manager.delete_topic_dir(user_id, "non_existent")
        
        # 尝试删除根目录
        assert not base_path_manager.delete_topic_dir(user_id, "")
    
    def test_rename_topic_dir(self, base_path_manager):
        """测试重命名主题目录"""
        user_id = "test_user_rename"
        
        # 创建测试目录
        base_path_manager.create_topic_dir(user_id, "old_name")
        old_path = base_path_manager.get_topic_path(user_id, "old_name")
        assert old_path.exists()
        
        # 重命名目录
        success, new_path_str = base_path_manager.rename_topic_dir(user_id, "old_name", "new_name")
        assert success
        assert new_path_str == "new_name"
        
        new_path = base_path_manager.get_topic_path(user_id, "new_name")
        assert new_path.exists()
        assert not old_path.exists()
        
        # 尝试重命名到已存在的目录
        base_path_manager.create_topic_dir(user_id, "another_dir")
        success, _ = base_path_manager.rename_topic_dir(user_id, "new_name", "another_dir")
        assert not success
        
        # 尝试重命名根目录
        success, _ = base_path_manager.rename_topic_dir(user_id, "", "root_renamed")
        assert not success
    
    def test_move_topic_dir(self, base_path_manager):
        """测试移动主题目录"""
        user_id = "test_user_move"
        
        # 创建测试目录
        base_path_manager.create_topic_dir(user_id, "source_dir")
        base_path_manager.create_topic_dir(user_id, "target_dir")
        
        source_path = base_path_manager.get_topic_path(user_id, "source_dir")
        (source_path / "__id_move_doc__.md").write_text("测试移动文档")
        
        # 移动目录
        success, new_path = base_path_manager.move_topic_dir(user_id, "source_dir", "target_dir")
        assert success
        assert new_path == "target_dir/source_dir"
        
        # 验证移动结果
        moved_path = base_path_manager.get_topic_path(user_id, "target_dir/source_dir")
        assert moved_path.exists()
        assert not source_path.exists()
        assert (moved_path / "__id_move_doc__.md").exists()
        
        # 尝试移动不存在的目录
        success, _ = base_path_manager.move_topic_dir(user_id, "non_existent", "target_dir")
        assert not success
        
        # 尝试移动到已存在的同名目录
        base_path_manager.create_topic_dir(user_id, "another_source")
        base_path_manager.create_topic_dir(user_id, "another_target/another_source")
        success, _ = base_path_manager.move_topic_dir(user_id, "another_source", "another_target")
        assert not success
        
        # 尝试移动根目录
        success, _ = base_path_manager.move_topic_dir(user_id, "", "target_dir")
        assert not success
    
    def test_copy_topic_dir(self, base_path_manager):
        """测试复制主题目录"""
        user_id = "test_user_copy"
        
        # 创建测试目录
        base_path_manager.create_topic_dir(user_id, "source_dir")
        base_path_manager.create_topic_dir(user_id, "target_dir")
        
        source_path = base_path_manager.get_topic_path(user_id, "source_dir")
        (source_path / "__id_copy_doc__.md").write_text("测试复制文档")
        
        # 复制目录
        success, new_path = base_path_manager.copy_topic_dir(user_id, "source_dir", "target_dir")
        assert success
        assert new_path == "target_dir/source_dir"
        
        # 验证复制结果
        copied_path = base_path_manager.get_topic_path(user_id, "target_dir/source_dir")
        assert copied_path.exists()
        assert source_path.exists()  # 原目录仍存在
        assert (copied_path / "__id_copy_doc__.md").exists()
        
        # 尝试复制不存在的目录
        success, _ = base_path_manager.copy_topic_dir(user_id, "non_existent", "target_dir")
        assert not success
        
        # 尝试复制到已存在的同名目录
        base_path_manager.create_topic_dir(user_id, "another_source")
        base_path_manager.create_topic_dir(user_id, "another_target/another_source")
        success, _ = base_path_manager.copy_topic_dir(user_id, "another_source", "another_target")
        assert not success
        
        # 尝试复制根目录
        success, _ = base_path_manager.copy_topic_dir(user_id, "", "target_dir")
        assert not success
    
    def test_merge_topic_dirs(self, base_path_manager):
        """测试合并主题目录"""
        user_id = "test_user_merge"
        
        # 创建源目录结构
        base_path_manager.create_topic_dir(user_id, "source")
        base_path_manager.create_topic_dir(user_id, "source/subtopic")
        source_path = base_path_manager.get_topic_path(user_id, "source")
        (source_path / "__id_source_doc1__.md").write_text("源文档1")
        (source_path / "subtopic" / "__id_source_doc2__.md").write_text("源文档2")
        
        # 创建目标目录结构
        base_path_manager.create_topic_dir(user_id, "target")
        base_path_manager.create_topic_dir(user_id, "target/subtopic")
        target_path = base_path_manager.get_topic_path(user_id, "target")
        (target_path / "__id_target_doc1__.md").write_text("目标文档1")
        (target_path / "subtopic" / "__id_target_doc2__.md").write_text("目标文档2")
        
        # 合并目录（不覆盖）
        assert base_path_manager.merge_topic_dirs(user_id, "source", "target", overwrite=False)
        
        # 验证合并结果
        merged_target = base_path_manager.get_topic_path(user_id, "target")
        assert (merged_target / "__id_source_doc1__.md").exists()
        assert (merged_target / "__id_target_doc1__.md").exists()
        assert (merged_target / "subtopic" / "__id_source_doc2__.md").exists()
        assert (merged_target / "subtopic" / "__id_target_doc2__.md").exists()
        
        # 源目录仍然存在
        assert source_path.exists()
        
        # 测试覆盖模式
        (source_path / "__id_target_doc1__.md").write_text("覆盖的文档内容")
        assert base_path_manager.merge_topic_dirs(user_id, "source", "target", overwrite=True)
        assert (merged_target / "__id_target_doc1__.md").read_text() == "覆盖的文档内容"
        
        # 尝试合并不存在的目录
        assert not base_path_manager.merge_topic_dirs(user_id, "non_existent", "target")
        assert not base_path_manager.merge_topic_dirs(user_id, "source", "non_existent")
