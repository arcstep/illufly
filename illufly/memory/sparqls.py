
TURTLE_QUERY_PREDICATES_TEMPLATES = """
PREFIX t: <http://illufly.com/template#>

SELECT ?sub ?obj
WHERE {
  ?sub t:format ?obj .
}
"""

TURTLE_QUERY_NEWEST_TRIPLES = """
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX t: <http://illufly.com/template#>

SELECT ?subject ?predicate ?object
WHERE {
  ?subject ?predicate ?object .

  # 排除模板类三元组（如 t:format）
  FILTER (?predicate != t:format)
  
  FILTER (?predicate != prov:wasInvalidatedBy)

  # 排除被标记为过期的内容
  FILTER NOT EXISTS {
    # 查找与当前三元组相关的失效活动
    ?subject prov:wasInvalidatedBy ?activity .
    ?activity prov:invalidatedPredicate ?predicate ;
              prov:invalidatedObject ?object .
  }

  # 过滤 prov:Activity 类型的资源
  FILTER NOT EXISTS { ?subject a prov:Activity }
}
"""

