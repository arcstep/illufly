import pytest
from illufly.utils import extract_segments

class TestExtractSegments:
    """测试extract_segments函数的各种情况"""

    def test_basic_extraction(self):
        """测试基本的标记提取功能"""
        text = "前导文本\n```turtle\nrdf内容\n第二行\n```\n后续文本"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["rdf内容\n第二行"]

    def test_include_markers(self):
        """测试包含标记的情况"""
        text = "前导文本\n```turtle\nrdf内容\n```\n后续文本"
        result = extract_segments(text, ("```turtle", "```"), include_markers=True)
        assert result == ["```turtle\nrdf内容\n```"]

    def test_multiple_segments(self):
        """测试多个段落的提取"""
        text = "```turtle\n第一段\n```\n中间文本\n```turtle\n第二段\n```"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["第一段", "第二段"]
        
    def test_same_line_markers(self):
        """测试开始和结束标记在同一行的情况"""
        text = "前导文本\n```turtle 这是内容 ```\n后续文本"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["这是内容"]
        
    def test_same_line_markers_with_include(self):
        """测试开始和结束标记在同一行且包含标记的情况"""
        text = "前导文本\n```turtle 这是内容 ```\n后续文本"
        result = extract_segments(text, ("```turtle", "```"), include_markers=True)
        assert "```turtle" in result[0]
        assert "```" in result[0]
        assert "这是内容" in result[0]

    def test_mixed_markers(self):
        """测试混合标记的情况"""
        text = "```turtle\n三元组\n```\n```json\n{'key':'value'}\n```"
        turtle_result = extract_segments(text, ("```turtle", "```"))
        json_result = extract_segments(text, ("```json", "```"))
        
        assert turtle_result == ["三元组"]
        assert json_result == ["{'key':'value'}"]

    def test_nested_markers(self):
        """测试嵌套标记的处理"""
        text = "```turtle\n这里是```inner```嵌套内容\n```"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["这里是```inner```嵌套内容"]

    def test_unclosed_markers(self):
        """测试未闭合标记的处理"""
        text = "```turtle\n未闭合内容"
        
        # 非严格模式下应返回未闭合内容
        result = extract_segments(text, ("```turtle", "```"), strict=False)
        assert result == ["未闭合内容"]
        
        # 严格模式下应返回空列表
        strict_result = extract_segments(text, ("```turtle", "```"), strict=True)
        assert strict_result == []

    def test_no_markers(self):
        """测试不存在标记的情况"""
        text = "没有任何标记的普通文本"
        
        # 非严格模式下应返回原始文本
        result = extract_segments(text, ("```turtle", "```"), strict=False)
        assert result == [text]
        
        # 严格模式下应返回空列表
        strict_result = extract_segments(text, ("```turtle", "```"), strict=True)
        assert strict_result == []

    def test_empty_text(self):
        """测试空文本的情况"""
        text = ""
        result = extract_segments(text, ("```turtle", "```"))
        assert result == []

    def test_none_marker(self):
        """测试标记为None的情况"""
        text = "有内容的文本"
        result = extract_segments(text, None)
        assert result == [text]

    def test_case_insensitivity(self):
        """测试大小写不敏感性"""
        text = "```TURTLE\n大写标记内容\n```"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["大写标记内容"]
        
        # 反向测试
        lower_text = "```turtle\n小写标记内容\n```"
        result = extract_segments(lower_text, ("```TURTLE", "```"))
        assert result == ["小写标记内容"]

    def test_multiline_complex_content(self):
        """测试复杂的多行内容"""
        text = (
            "# 文档\n"
            "这里是介绍\n"
            "```turtle\n"
            "@prefix ex: <http://example.org/> .\n"
            "ex:Resource a ex:Type ;\n"
            "    ex:property \"value\" .\n"
            "```\n"
            "这里是解释\n"
            "```json\n"
            "{\n"
            '  "key": "value",\n'
            '  "array": [1, 2, 3]\n'
            "}\n"
            "```\n"
            "结尾文本"
        )
        
        turtle_result = extract_segments(text, ("```turtle", "```"))
        json_result = extract_segments(text, ("```json", "```"))
        
        assert "@prefix ex:" in turtle_result[0]
        assert '"array": [1, 2, 3]' in json_result[0]

    def test_partial_marker_match(self):
        """测试部分标记匹配的情况"""
        text = "这里有个```不完整的标记\n和另一个不完整的```标记"
        result = extract_segments(text, ("```turtle", "```"))
        
        # 应该返回原文，因为没有完整匹配的标记对
        assert result == [text]

    def test_whitespace_handling(self):
        """测试空白处理"""
        text = "```turtle    \n  缩进内容  \n  另一行  \n```"
        result = extract_segments(text, ("```turtle", "```"))
        assert result == ["缩进内容  \n  另一行"]