import pytest
from pathlib import Path
from illufly.prompt import PromptTemplate, load_prompt_template

class TestSystemTemplate:
    """PromptTemplate 类的测试套件
    
    PromptTemplate 类实现了基于 Mustache 语法的模板系统，支持以下功能：
    1. 基本变量替换
    2. 条件渲染（section和inverted section）
    3. 嵌套对象访问
    4. 数组迭代
    5. 子模板引用
    
    Mustache 的关键行为规则：
    1. 真/假值判断：
       - 空对象（{}）被视为假值
       - 空数组（[]）被视为假值
       - 空字符串被视为假值
       - null/None 被视为假值
       - 其他非空值被视为真值
    
    2. Section 渲染规则：
       - {{#section}} 当值为真时渲染
       - {{^section}} 当值为假或不存在时渲染
       - 嵌套的 section 独立判断真假值
    
    3. 变量访问规则：
       - 支持点号访问嵌套属性（user.name.first）
       - 在数组迭代中使用 {{.}} 访问当前元素
       - 在数组迭代上下文中可直接访问元素的属性
    """

    def test_basic_template_loading(self, template_dir):
        """测试基本模板加载功能
        
        验证：
        1. 从文件加载简单模板
        2. 从文件加载嵌套模板
        3. 直接使用文本创建模板
        """
        # 确保template_dir是Path对象
        assert isinstance(template_dir, Path)
        
        # 测试简单模板加载
        template = PromptTemplate(template_id="simple", template_folder=template_dir)
        assert template.text == "Hello, {{name}}!"

    def test_template_metadata(self, template_dir):
        """测试模板元数据功能
        
        验证：
        1. 模板来源标记（source）
        2. 创建时间记录（created_at）
        3. 变量列表提取（variables）
        """
        # 测试从文件加载的模板
        template = PromptTemplate(template_id="simple", template_folder=template_dir)
        assert template.metadata['source'] == 'simple'
        assert 'created_at' in template.metadata
        assert 'variables' in template.metadata
        assert 'name' in template.metadata['variables']

        # 测试自定义文本模板
        template = PromptTemplate(text="Hello, {{user}}!")
        assert template.metadata['source'] == 'TEXT'
        assert 'created_at' in template.metadata
        assert 'variables' in template.metadata
        assert 'user' in template.metadata['variables']

    def test_nested_object_access(self):
        """测试嵌套对象访问
        
        验证：
        1. 多层属性访问（user.name.first）
        2. 属性不存在时的处理
        3. 空对象的处理
        """
        template = PromptTemplate(text="""
            {{user.name.first}} {{user.name.last}}
            {{user.email}}
            {{company.address.city}}
        """)

        data = {
            "user": {
                "name": {
                    "first": "John",
                    "last": "Doe"
                },
                "email": "john@example.com"
            },
            "company": {
                "address": {
                    "city": "Beijing"
                }
            }
        }

        result = template.format(data)
        assert "John Doe" in result
        assert "john@example.com" in result
        assert "Beijing" in result

    def test_array_iteration(self):
        """测试数组迭代功能
        
        验证：
        1. 基本数组迭代
        2. 数组元素属性访问
        3. 嵌套数组处理
        4. 空数组处理
        """
        template = PromptTemplate(text="""{{#posts}}
            <h2>{{title}}</h2>
            <p>{{content}}</p>
            {{#tags}}
            <span>{{.}}</span>
            {{/tags}}
        {{/posts}}""")

        data = {
            "posts": [
                {
                    "title": "Post One",
                    "content": "Content of post one",
                    "tags": ["tech", "news"]
                },
                {
                    "title": "Post Two",
                    "content": "Content of post two",
                    "tags": []  # 空数组应该被视为假值
                }
            ]
        }

        result = template.format(data)
        assert "Post One" in result
        assert "Content of post one" in result
        assert "Post Two" in result
        assert "Content of post two" in result
        assert "<span>tech</span>" in result
        assert "<span>news</span>" in result
        
        # 测试空数组
        empty_data = {
            "posts": []  # 空数组应该被视为假值
        }
        result = template.format(empty_data)
        assert "Post One" not in result
        assert "Post Two" not in result

    def test_complex_nested_structure(self):
        """测试复杂嵌套结构
        
        验证：
        1. 对象和数组的混合嵌套
        2. 多层条件渲染
        3. 深层属性访问
        4. 空值处理
        """
        template = PromptTemplate(text="""
            {{#company}}
                {{name}}
                {{#departments}}
                    {{name}}
                    {{#employees}}
                        {{#name}}{{first}} {{last}}{{/name}}
                        {{#skills}}
                            {{.}}
                        {{/skills}}
                    {{/employees}}
                {{/departments}}
            {{/company}}
        """)

        data = {
            "company": {
                "name": "Tech Corp",
                "departments": [
                    {
                        "name": "Engineering",
                        "employees": [
                            {
                                "name": {"first": "John", "last": "Doe"},
                                "skills": ["Python", "Java"]
                            },
                            {
                                "name": {"first": "Jane", "last": "Smith"},
                                "skills": ["C++", "Rust"]
                            }
                        ]
                    }
                ]
            }
        }

        result = template.format(data)
        assert "Tech Corp" in result
        assert "Engineering" in result
        assert "John Doe" in result
        assert "Jane Smith" in result
        assert "Python" in result
        assert "Rust" in result

        # 测试空对象行为
        empty_data = {
            "company": {}  # 空对象应该被视为假值
        }
        result = template.format(empty_data)
        assert "Tech Corp" not in result
        assert "Engineering" not in result

    def test_conditional_with_nested_data(self):
        """测试嵌套数据的条件渲染
        
        验证：
        1. 基于对象存在的条件渲染
        2. 基于对象属性的条件渲染
        3. 空对象的处理（触发inverted section）
        4. 默认值处理
        """
        template = PromptTemplate(text="""
            {{#user}}
                {{#name}}
                    {{#first}}Hello, {{first}}!{{/first}}
                    {{^first}}Hello, Anonymous!{{/first}}
                {{/name}}
                {{^name}}
                    Hello, Unnamed User!
                {{/name}}
            {{/user}}
            {{^user}}
                Hello, Guest!
            {{/user}}
        """)

        # 完整数据
        result = template.format({"user": {"name": {"first": "John"}}})
        assert "Hello, John!" in result

        # 空name对象 - 因为是假值，会触发 {{^name}}
        result = template.format({"user": {"name": {}}})
        assert "Hello, Unnamed User!" in result

        # name对象没有first属性
        result = template.format({"user": {"name": {"last": "Doe"}}})
        assert "Hello, Anonymous!" in result

        # user是空对象，被视为假值
        result = template.format({"user": {}})
        assert "Hello, Guest!" in result  # 不是 "Hello, Unnamed User!"

        # 没有user
        result = template.format({})
        assert "Hello, Guest!" in result

    def test_error_handling(self, template_dir):
        """测试错误处理
        
        验证：
        1. 无效模板ID处理
        2. 无效子模板处理
        3. 参数验证
        4. 错误消息的准确性
        """
        # 测试不存在的模板
        with pytest.raises(ValueError) as e:
            PromptTemplate(template_id="nonexistent")
        assert "无效的模板ID" in str(e.value)

        with pytest.raises(ValueError) as e:
            PromptTemplate(template_id="nonexistent", template_folder=template_dir)
        assert "无效的模板ID" in str(e.value)

        # 测试无效的部分模板
        with pytest.raises(ValueError) as e:
            PromptTemplate(template_id="invalid_nested", template_folder=template_dir)

        # 测试无效的参数组合
        with pytest.raises(ValueError):
            PromptTemplate()  # 没有提供任何参数

        with pytest.raises(ValueError):
            PromptTemplate(template_folder=template_dir)  # 只提供template_folder

    def test_partial_template_resolution(self, template_dir):
        """测试子模板解析
        
        验证：
        1. 基本子模板引用
        2. 嵌套子模板处理
        3. 子模板文件不存在的错误处理
        4. 子模板路径解析
        """
        # 测试行中的子模板
        inline_dir = template_dir / "inline_nested"
        inline_dir.mkdir()
        (inline_dir / "main.mu").write_text("Start {{>header}} Middle {{>footer}} End")
        (inline_dir / "header.mu").write_text("HEADER")
        (inline_dir / "footer.mu").write_text("FOOTER")

        template = PromptTemplate(template_id="inline_nested", template_folder=template_dir)
        assert template.text == "Start HEADER Middle FOOTER End"

    def test_template_caching(self, template_dir):
        """测试模板缓存"""
        # 测试相同参数的模板加载是否使用缓存
        template1 = PromptTemplate(template_id="simple", template_folder=template_dir)
        template2 = PromptTemplate(template_id="simple", template_folder=template_dir)
        assert template1.text == template2.text

        # 修改模板文件
        (template_dir / "simple" / "main.mu").write_text("Modified content")
        template3 = PromptTemplate(template_id="simple", template_folder=template_dir)
        assert template3.text == template1.text  # 应该返回缓存的内容

        # 清除缓存后重新加载
        load_prompt_template.cache_clear()
        template4 = PromptTemplate(template_id="simple", template_folder=template_dir)
        assert template4.text == "Modified content"

    def test_template_formatting(self):
        """测试模板格式化"""
        # 测试简单替换
        template = PromptTemplate(text="Hello, {{name}}!")
        result = template.format({"name": "Alice"})
        assert result == "Hello, Alice!"

        # 测试多变量替换
        template = PromptTemplate(text="{{greeting}}, {{name}}!")
        result = template.format({"greeting": "Hi", "name": "Bob"})
        assert result == "Hi, Bob!"

    def test_template_variables(self):
        """测试模板变量提取"""
        # 测试简单变量
        template = PromptTemplate(text="Hello, {{name}}!")
        assert template.variables == {'name'}

        # 测试多个变量
        template = PromptTemplate(text="{{greeting}}, {{name}}!")
        assert template.variables == {'greeting', 'name'}

        # 测试重复变量
        template = PromptTemplate(text="{{name}}, {{name}}!")
        assert template.variables == {'name'}

        # 测试嵌套结构中的变量
        template = PromptTemplate(text="{{user.name}}, {{user.age}}!")
        assert template.variables == {'user.name', 'user.age'}
