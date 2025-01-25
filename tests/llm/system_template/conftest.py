import pytest
from pathlib import Path
import shutil

@pytest.fixture
def template_dir(tmp_path):
    # 创建测试模板目录
    test_template_dir = tmp_path / "test_templates"
    test_template_dir.mkdir()
    
    # 简单模板
    simple_dir = test_template_dir / "simple"
    simple_dir.mkdir()
    (simple_dir / "main.mu").write_text("Hello, {{name}}!")

    # 无效嵌套模板
    invalid_nested_dir = test_template_dir / "invalid_nested"
    invalid_nested_dir.mkdir()
    (invalid_nested_dir / "main.mu").write_text("Hello, {{>invalid_nested}}!")

    # 嵌套模板
    nested_dir = test_template_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "main.mu").write_text("""
    {{>header}}
    Content: {{content}}
    {{>footer}}
    """)
    (nested_dir / "header.mu").write_text("=== Header ===")
    (nested_dir / "footer.mu").write_text("=== Footer ===")
    
    yield test_template_dir  # 提供测试目录
    
    # 清理：删除测试目录
    shutil.rmtree(test_template_dir, ignore_errors=True)