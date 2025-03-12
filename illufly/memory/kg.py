from typing import Dict, List, Tuple, Optional, Any, Set, Union
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS
from rdflib.plugins.sparql import prepareQuery

import logging
import uuid
from datetime import datetime

from ..utils import extract_segments
from ..community import BaseVectorDB, BaseChat
from ..rocksdb import IndexedRocksDB, default_rocksdb
from ..prompt import PromptTemplate
from .sparqls import (
    TURTLE_QUERY_PREDICATES_TEMPLATES,
    TURTLE_QUERY_NEWEST_TRIPLES
)

class KnowledgeGraph:
    """RDF知识图谱包装类
    
    管理用户的知识图谱，支持从文本生成图谱、解决冲突和查询相关知识

    1. 生成记忆逻辑
    - 根据问题从向量库中检索已存在的三元组turtle表达式及其自然语言表述
    - 将已存在三元组与用户输入的文本一起构建大模型提示语
    - 使用大模型生成Turtle表达式（包括所有主语谓语宾语的中文标签）
    - 提取turtle表达式：拆解为单个三元组清单和谓词清单
    - 对于新的谓词，使用大模型生成谓词模板（包括一主一宾、一主多宾、多主一宾、多主多宾等模式）
    - 将三元组清单和谓词清单，按谓词模板生成自然语言表述
        - 保存到rocksdb：
            - 三元组的turtle表达式，建为三元组主语谓语宾语的hash值，值为turtle表达式
            - 谓词模板，键为谓词hash值，值为谓词模板
        - 更新到向量数据库：针对三元组的自然语言表述嵌入，检索三元组turtle表达式、自然语言表述
        - 更新到图谱：针对三元组turtle表达式
    - 解决图谱合并时的概念冲突
        - 提取冲突：从注释中识别冲突
        - 解决冲突：从图中移除有冲突的三元组

    2. 查询记忆逻辑
    - 根据问题从向量数据库中检索已存在的三元组turtle表达式
    - 根据三元组检索子图，并提取所有三元组
    - 根据谓词模板生成自然语言表述，作为记忆返回

    3. 初始化向量库和图谱的逻辑
    - 读取rocksdb中用户所有的三元组数据
        - 初始化向量数据库，为每个用户建立独立的集合，针对三元组的自然语言表述嵌入，检索三元组turtle表达式
        - 为每个用户初始化独立的图谱，将三元组turtle表达式添加到图谱
    """
    
    def __init__(
        self,
        llm: Optional[BaseChat] = None,
        vector_db: Optional[BaseVectorDB] = None,
        docs_db: Optional[IndexedRocksDB] = None,
        prompt_template: Optional[PromptTemplate] = None
    ):
        """初始化知识图谱"""
        self.llm = llm
        self.vector_db = vector_db
        self.docs_db = docs_db or default_rocksdb

        self.prompt_template = prompt_template or PromptTemplate(template_id="turtle-nl")
        self.graph = Graph()
        self._logger = logging.getLogger(__name__)

    async def extract(self, text: str, user_id: str = None) -> Graph:
        """从文本生成知识并添加到图谱
        
        Args:
            user_id: 用户ID
            text: 输入文本
            
        Returns:
            更新后的RDF图谱
        """
        user_id = user_id or "default"
        # 检索历史信息
        existing_turtles = await self._retrieve_existing_turtles(text, user_id)
        # 组合提示并生成Turtle表达式
        turtle_data = await self._generate_turtle(
            prompt=text,
            user_id=user_id,
            existing_turtles=existing_turtles
        )
        
        # 解析并合并到图谱
        new_graph = Graph()
        if turtle_data and turtle_data.strip():
            try:
                new_graph.parse(data=turtle_data, format="turtle")
            except Exception as e:
                raise Exception(f"解析Turtle数据时出错: {e}")
        
        # 合并图谱
        await self._resolve_conflicts(new_graph)
            
        # 保存到向量数据库
        await self._save_to_vector_db(new_graph, user_id)
        
        return self.graph
    
    async def query(self, text: str, user_id: str = None) -> str:
        """根据文本查询相关知识
        
        Args:
            user_id: 用户ID
            text: 查询文本
            
        Returns:
            格式化的知识文本
        """
        user_id = user_id or "default"
        results = await self.vector_db.query(
            texts=[text],
            collection_name=user_id,
            n_results=5
        )
        
        results = results["documents"][0] if results["documents"][0] else []
        return "\n".join(results)

    
    async def _retrieve_existing_turtles(self, text: str, user_id: str = None) -> str:
        """从向量数据库检索相关历史信息"""
        user_id = user_id or "default"
        if not self.vector_db:
            return "", self.namespaces
        
        # 从向量数据库检索相似三元组
        result = await self.vector_db.query(texts=[text], collection_name=user_id, n_results=5)
        print(result)
        return "\n".join(result["documents"][0]) if result["documents"][0] else ""

    async def generate_turtle(self, content: str, existing_turtles: str = None, user_id: str = None) -> str:
        """使用大模型生成Turtle表达式"""
        user_id = user_id or "default"
        if not self.llm:
            # 如果没有提供大模型，返回空字符串
            return ""
        
        system_prompt = self.prompt_template.format({
            "namespacePrefix": f"http://illufly.com/u-{user_id}/memory#",
            "namespaceURI": "m",
            "content": content,
            "existing_turtles": existing_turtles or ""
        })
        final_text = ""
        async for x in self.llm.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请开始"}
        ]):
            if x.message_type == "text_chunk":
                print(x.text, end="")
                final_text += x.text
        turtles = extract_segments(final_text, ("```turtle", "```"))

        try:
            g = Graph()
            g.parse(data=turtles[0], format="turtle")
            return g
        except Exception as e:
            raise Exception(f"解析Turtle数据时出错: {e}")

    @classmethod
    def _extract_local_name(cls, uri: URIRef) -> str:
        """从 URI 中提取最后的路径或片段作为名称"""
        uri_str = str(uri)
        if "#" in uri_str:
            return uri_str.split("#")[-1]
        elif "/" in uri_str:
            return uri_str.split("/")[-1]
        else:
            return uri_str

    @classmethod
    def get_turtle(cls, graph: Graph) -> str:
        """将图谱转换为Turtle表达式"""
        return graph.serialize(format="turtle")

    @classmethod
    def _get_predicates_templates(cls, graph: Graph) -> Set[URIRef]:
        """获取图谱中的谓词"""
        template_mapping = {}
        for row in graph.query(TURTLE_QUERY_PREDICATES_TEMPLATES):
            template_mapping[str(row.sub)] = str(row.obj)
        return template_mapping

    @classmethod
    def get_newest_triples(cls, graph: Graph) -> List[Tuple[URIRef, URIRef, URIRef]]:
        """获取图谱中的最新三元组"""
        return list(graph.query(TURTLE_QUERY_NEWEST_TRIPLES))

    @classmethod
    def get_triple_texts(cls, graph: Graph) -> List[Tuple[URIRef, URIRef, URIRef, str]]:
        """获取四元组文本"""
        triples = cls.get_newest_triples(graph)
        def default_template(p: URIRef) -> str:
            return "{subject} " + cls._extract_local_name(p) + " {object}"
        templates = cls._get_predicates_templates(graph)

        return [
        (s, p, o,
        templates.get(str(p), default_template(p)).format(
            subject=cls._extract_local_name(s),
            object=cls._extract_local_name(o)
        ))
        for s, p, o
        in triples]

    async def _save_to_vector_db(self, new_graph: Graph, user_id: str = None) -> None:
        """将图谱中的三元组保存到向量数据库"""
        user_id = user_id or "default"
        if not self.vector_db:
            return
        
        # 处理所有主语
        for subject in set(s for s, _, _ in new_graph):
            # 获取主语的所有标签和注释
            labels = [str(label) for label in new_graph.objects(subject, RDFS.label)]
            comments = [str(comment) for comment in new_graph.objects(subject, RDFS.comment)]
            
            # 获取主语的所有三元组
            triples = list(new_graph.triples((subject, None, None)))
            
            # 组合文档内容
            doc_text = " ".join([
                f"{str(s)} {str(p)} {str(o)}" for s, p, o in triples
            ])
            if labels:
                doc_text += " 标签: " + ", ".join(labels)
            if comments:
                doc_text += " 描述: " + ", ".join(comments)
            
            self._logger.info(f"嵌入三元组描述: {doc_text}")
            await self.vector_db.add(texts=[doc_text], collection_name=user_id)
    
    @classmethod
    def extract_related_subgraph(cls, graph: Graph, triples: List[Tuple[URIRef, URIRef, URIRef]]) -> Graph:
        subgraph = Graph()
        visited = set()

        def traverse(node):
            if node in visited:
                return
            visited.add(node)
            for s, p, o in graph.triples((node, None, None)):
                subgraph.add((s, p, o))
                if isinstance(o, URIRef):
                    traverse(o)
            for s, p, o in graph.triples((None, None, node)):
                subgraph.add((s, p, o))
                if isinstance(s, URIRef):
                    traverse(s)

        for row in triples:
            # row 可以是三元组或增加了谓词模板文本的四元组
            subgraph.add((row[0], row[1], row[2]))
            traverse(row[0])
            traverse(row[2])

        return subgraph

