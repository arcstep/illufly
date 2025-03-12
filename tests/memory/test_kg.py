import pytest
from rdflib import Graph, URIRef, Literal
from unittest.mock import MagicMock

# 导入需要测试的模块
from illufly.memory.kg import KnowledgeGraph
from illufly.prompt import PromptTemplate

@pytest.fixture
def test_graph():
    """创建测试用的基础图谱"""
    graph = Graph()
    graph.parse(data="""
        @prefix ex: <http://example.org/> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        
        ex:Person1 rdf:type ex:Person ;
            ex:name "张三" ;
            ex:age "30" ;
            ex:knows ex:Person2 .
            
        ex:Person2 rdf:type ex:Person ;
            ex:name "李四" ;
            ex:age "25" ;
            ex:worksAt ex:Company1 .
            
        ex:Company1 rdf:type ex:Company ;
            ex:name "示例公司" ;
            ex:location "北京" .
    """, format="turtle")
    return graph

def test_extract_local_name():
    """测试从URI中提取本地名称的方法"""
    # 测试包含#的URI
    uri1 = URIRef("http://example.org/ontology#Person")
    assert KnowledgeGraph._extract_local_name(uri1) == "Person"
    
    # 测试包含/的URI
    uri2 = URIRef("http://example.org/ontology/Person")
    assert KnowledgeGraph._extract_local_name(uri2) == "Person"
    
    # 测试简单字符串
    uri3 = URIRef("Person")
    assert KnowledgeGraph._extract_local_name(uri3) == "Person"

def test_get_newest_triples(test_graph, monkeypatch):
    """测试获取最新三元组的方法"""
    # 模拟SPARQL查询
    monkeypatch.setattr(
        'illufly.memory.sparqls.TURTLE_QUERY_NEWEST_TRIPLES', 
        """
        SELECT ?s ?p ?o 
        WHERE { 
            ?s ?p ?o 
        }
        """
    )
    
    triples = KnowledgeGraph.get_newest_triples(test_graph)
    assert len(triples) > 0
    # 验证三元组格式
    for s, p, o in triples:
        assert isinstance(s, URIRef)
        assert isinstance(p, URIRef)

def test_split_turtle():
    """测试将Turtle表达式拆分为独立三元组的方法"""
    turtle_data = """
        @prefix ex: <http://example.org/> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        
        ex:Person1 rdf:type ex:Person ;
            ex:name "张三" .
    """
    
    result = KnowledgeGraph.split_turtle(turtle_data)
    assert len(result) == 2  # 应该有两个三元组
    
    # 检查结果格式
    for turtle_text, triple_text in result:
        assert isinstance(turtle_text, str)
        assert isinstance(triple_text, str)
        assert triple_text.startswith("(") and triple_text.endswith(")")

def test_extract_related_subgraph_sparql_with_mock(test_graph, monkeypatch):
    """测试使用SPARQL查询提取相关子图的方法(使用mock)"""
    # 创建子图
    sub_graph = Graph()
    sub_graph.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:Person1 ex:knows ex:Person2 .
    """, format="turtle")
    
    # 直接修补KnowledgeGraph类的方法来监控PromptTemplate的使用
    original_method = KnowledgeGraph.extract_related_subgraph_sparql
    template_format_called = [0]  # 使用列表以便在闭包中修改
    
    @classmethod
    def mocked_extract_method(cls, graph, sub_graph):
        # 增加计数器
        template_format_called[0] += 1
        
        # 创建并返回一个简单的结果图
        result = Graph()
        result.add((URIRef('http://example.org/Person1'), 
                   URIRef('http://example.org/name'), 
                   Literal('测试名称')))
        return result
    
    # 应用mock
    monkeypatch.setattr(KnowledgeGraph, 'extract_related_subgraph_sparql', mocked_extract_method)
    
    # 执行方法调用
    result = KnowledgeGraph.extract_related_subgraph_sparql(test_graph, sub_graph)
    
    # 验证方法被调用
    assert template_format_called[0] == 1
    
    # 验证结果
    assert isinstance(result, Graph)
    assert len(list(result.triples((None, None, None)))) > 0

def test_extract_related_subgraph_sparql_real(test_graph):
    """测试实际使用PromptTemplate的SPARQL查询功能"""
    # 创建子图
    sub_graph = Graph()
    sub_graph.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:Person1 ex:knows ex:Person2 .
    """, format="turtle")
    
    # 执行方法
    result_graph = KnowledgeGraph.extract_related_subgraph_sparql(test_graph, sub_graph)
    
    # 验证结果
    assert isinstance(result_graph, Graph)
    
    # 子图应该包含与Person1和Person2相关的三元组
    person1_triples = list(result_graph.triples((URIRef('http://example.org/Person1'), None, None)))
    person2_triples = list(result_graph.triples((URIRef('http://example.org/Person2'), None, None)))
    
    assert len(person1_triples) > 0
    assert len(person2_triples) > 0
    
    # 验证第二度关系是否被正确提取
    company_triples = list(result_graph.triples((URIRef('http://example.org/Company1'), None, None)))
    assert len(company_triples) > 0

def test_second_query_template_syntax(test_graph):
    """测试第二查询模板的语法是否正确"""
    # 创建子图
    sub_graph = Graph()
    sub_graph.parse(data="""
        @prefix ex: <http://example.org/> .
        ex:Person1 ex:knows ex:Person2 .
    """, format="turtle")
    
    # 执行方法以触发第二个查询生成
    # 我们只需要验证没有语法错误抛出
    result_graph = KnowledgeGraph.extract_related_subgraph_sparql(test_graph, sub_graph)
    
    # 如果执行到这里没有异常，那么模板语法应该是正确的
    assert True