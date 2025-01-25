import pytest
from pathlib import Path
from illufly.llm.system_template.template import SystemTemplate

def test_package_template_loading():
    """测试包内模板加载"""
    template = SystemTemplate(template_id="roles/assistant")
    assert isinstance(template.text, str)
    assert len(template.text) > 0

def test_local_template_loading(template_dir):
    """测试本地模板加载"""
    # 确保template_dir是Path对象
    assert isinstance(template_dir, Path)
    
    # 测试简单模板加载
    template = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template.text == "Hello, {{name}}!"

def test_local_nested_template(template_dir):
    """测试本地嵌套模板"""
    template = SystemTemplate(template_id="nested", template_folder=template_dir)
    assert "=== Header ===" in template.text
    assert "=== Footer ===" in template.text
    assert "Content: {{content}}" in template.text

def test_template_variables(template_dir):
    """测试模板变量提取"""
    template = SystemTemplate(text="{{name}} {{age}}", template_folder=template_dir)
    assert template.variables == {"name", "age"}

def test_template_validation(template_dir):
    """测试模板验证"""
    template = SystemTemplate(text="{{name}} {{age}}", template_folder=template_dir)
    assert template.validate({"name": "Alice", "age": 30}) is True
    assert template.validate({"name": "Alice"}) is False

def test_error_handling(template_dir):
    """测试错误处理"""
    # 测试不存在的模板
    with pytest.raises(RuntimeError):
        SystemTemplate(template_id="nonexistent", template_folder=template_dir)

    # 测试无效的部分模板
    with pytest.raises(FileNotFoundError):
        SystemTemplate(text="{{>invalid_partial}}", template_folder=template_dir)