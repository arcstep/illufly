import pytest
from pathlib import Path
from illufly.llm.system_template.template import SystemTemplate

def test_package_template_loading():
    """测试包内模板加载"""
    template = SystemTemplate(template_id="assistant")
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

def test_template_loading(template_dir):
    """测试模板加载"""
    # 测试简单模板加载
    template = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template.text == "Hello, {{name}}!"

    # 测试嵌套模板加载
    template = SystemTemplate(template_id="nested", template_folder=template_dir)
    assert "=== Header ===" in template.text
    assert "Content: {{content}}" in template.text
    assert "=== Footer ===" in template.text

def test_template_metadata(template_dir):
    """测试模板元数据"""
    # 测试从文件加载的模板
    template = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template.metadata['source'] == 'simple'
    assert 'created_at' in template.metadata
    assert 'variables' in template.metadata
    assert 'name' in template.metadata['variables']

    # 测试自定义文本模板
    template = SystemTemplate(text="Hello, {{user}}!")
    assert template.metadata['source'] == 'custom'
    assert 'created_at' in template.metadata
    assert 'variables' in template.metadata
    assert 'user' in template.metadata['variables']

def test_template_variables():
    """测试模板变量提取"""
    # 测试简单变量
    template = SystemTemplate(text="Hello, {{name}}!")
    assert template.variables == {'name'}

    # 测试多个变量
    template = SystemTemplate(text="{{greeting}}, {{name}}!")
    assert template.variables == {'greeting', 'name'}

    # 测试重复变量
    template = SystemTemplate(text="{{name}}, {{name}}!")
    assert template.variables == {'name'}

    # 测试嵌套结构中的变量
    template = SystemTemplate(text="{{user.name}}, {{user.age}}!")
    assert template.variables == {'user.name', 'user.age'}

def test_template_formatting():
    """测试模板格式化"""
    # 测试简单替换
    template = SystemTemplate(text="Hello, {{name}}!")
    result = template.format({"name": "Alice"})
    assert result == "Hello, Alice!"

    # 测试多变量替换
    template = SystemTemplate(text="{{greeting}}, {{name}}!")
    result = template.format({"greeting": "Hi", "name": "Bob"})
    assert result == "Hi, Bob!"

    # 测试缺失变量处理
    template = SystemTemplate(text="Hello, {{name}}!")
    with pytest.raises(ValueError):
        template.format({"age": 25})

def test_error_handling(template_dir):
    """测试错误处理"""
    # 测试不存在的模板
    with pytest.raises(ValueError) as e:
        SystemTemplate(template_id="nonexistent")
    assert "无效的模板ID" in str(e.value)

    with pytest.raises(ValueError) as e:
        SystemTemplate(template_id="nonexistent", template_folder=template_dir)
    assert "无效的模板ID" in str(e.value)

    # 测试无效的部分模板
    with pytest.raises(ValueError) as e:
        SystemTemplate(template_id="invalid_nested", template_folder=template_dir)

    # 测试无效的参数组合
    with pytest.raises(ValueError):
        SystemTemplate()  # 没有提供任何参数

    with pytest.raises(ValueError):
        SystemTemplate(template_folder=template_dir)  # 只提供template_folder

def test_nested_template_resolution(template_dir):
    """测试嵌套模板解析"""
    # 测试行中的子模板
    inline_dir = template_dir / "inline_nested"
    inline_dir.mkdir()
    (inline_dir / "main.mu").write_text("Start {{>header}} Middle {{>footer}} End")
    (inline_dir / "header.mu").write_text("HEADER")
    (inline_dir / "footer.mu").write_text("FOOTER")

    template = SystemTemplate(template_id="inline_nested", template_folder=template_dir)
    assert template.text == "Start HEADER Middle FOOTER End"

def test_template_caching(template_dir):
    """测试模板缓存"""
    # 测试相同参数的模板加载是否使用缓存
    template1 = SystemTemplate(template_id="simple", template_folder=template_dir)
    template2 = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template1.text == template2.text

    # 修改模板文件
    (template_dir / "simple" / "main.mu").write_text("Modified content")
    template3 = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template3.text == template1.text  # 应该返回缓存的内容

    # 清除缓存后重新加载
    from illufly.llm.system_template.hub import load_prompt_template
    load_prompt_template.cache_clear()
    template4 = SystemTemplate(template_id="simple", template_folder=template_dir)
    assert template4.text == "Modified content"
