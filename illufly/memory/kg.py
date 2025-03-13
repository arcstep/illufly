from typing import Dict, List, Tuple, Optional, Any, Set, Union
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS
from rdflib.plugins.sparql import prepareQuery
from datetime import datetime
from pydantic import BaseModel, Field

import logging
import uuid
from hashlib import md5

from ..utils import extract_segments
from ..community import BaseVectorDB, BaseChat
from ..rocksdb import IndexedRocksDB, default_rocksdb
from ..prompt import PromptTemplate
from ..mq.enum import BlockType
from .sparqls import (
    TURTLE_QUERY_NEWEST_TRIPLES,
    TURTLE_QUERY_WITHOUT_INVALIDATED
)

class Turtle(BaseModel):
    user_id: str = Field(..., description="用户ID")
    turtle_text: str = Field(..., description="Turtle表达式")
    turtle_id: str = Field(default_factory=lambda: str(uuid.uuid4().hex[:8]), description="Turtle表达式ID")
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp(), description="生成时间")
    
    model_config = {
        "arbitrary_types_allowed": True
    }

    @classmethod
    def get_user_prefix(cls, user_id: str) -> str:
        """获取用户前缀"""
        return f"kg-{user_id}"

    @classmethod
    def get_key(cls, user_id: str, turtle_id: str) -> str:
        """获取Turtle表达式键值"""
        return f"{cls.get_user_prefix(user_id)}:{turtle_id}"

class KnowledgeGraph:
    """知识图谱包装类"""
    
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
    def get_newest_triples(cls, graph: Graph) -> Graph:
        """获取图谱中的最新三元组"""
        return graph.query(TURTLE_QUERY_NEWEST_TRIPLES)
    
    @classmethod
    def get_without_invalidated(cls, graph: Graph) -> Graph:
        """获取图谱中的最新三元组（不包含失效的三元组）"""
        return graph.query(TURTLE_QUERY_WITHOUT_INVALIDATED)

    @classmethod
    def split_turtle(cls, turtle: str) -> List[Tuple[str, str]]:
        """将Turtle表达式拆分为独立的三元组"""
        # 解析 Turtle 数据到图
        g = Graph()
        g.parse(data=turtle, format="turtle")
        
        # 提取所有三元组
        triples = list(g.triples((None, None, None)))
        
        # 生成独立的三元组 Turtle 表达式（保留前缀）
        def serialize_single_triple(s, p, o):
            temp_g = Graph()
            # 继承原图的命名空间绑定
            for prefix, namespace in g.namespaces():
                temp_g.bind(prefix, namespace)
            temp_g.add((s, p, o))
            return temp_g.serialize(format="turtle").strip()
        
        # 输出每个独立三元组
        turtles = []
        for i, (s, p, o) in enumerate(triples, 1):
            sub = cls._extract_local_name(s)
            pred = cls._extract_local_name(p)
            obj = cls._extract_local_name(o)
            comment = f"({sub} - {pred} - {obj})"
            turtle_text = serialize_single_triple(s, p, o)
            turtles.append((turtle_text, comment))

        return turtles    
    
    @classmethod
    def extract_related_subgraph_sparql(
        cls,
        graph: Graph,
        sub_graph: Graph,
    ) -> Graph:
        """使用SPARQL查询提取相关子图"""
        subgraph = Graph()
        
        # 添加初始三元组并收集所有起始实体
        entities = set()
        
        for s, _, o in sub_graph:
            # 收集实体
            if isinstance(s, URIRef):
                entities.add(s)
            if isinstance(o, URIRef):
                entities.add(o)
        
        # 如果没有实体，直接返回空图
        if not entities:
            return subgraph
            
        entity_values = ", ".join(f"<{e}>" for e in entities)
        
        # 修改：避免使用可能与SPARQL语法冲突的模板变量格式
        # 使用一个不太可能出现在SPARQL中的占位符
        sparql_template = """
        CONSTRUCT { ?s ?p ?o }
        WHERE {
            { ?s ?p ?o . FILTER(?s IN (ENTITY_VALUES_PLACEHOLDER)) }
            UNION
            { ?s ?p ?o . FILTER(?o IN (ENTITY_VALUES_PLACEHOLDER)) }
        }
        """
        
        # 简单替换占位符而不使用模板引擎
        sparql_query = sparql_template.replace("ENTITY_VALUES_PLACEHOLDER", entity_values)
        
        # 执行SPARQL查询并添加结果到子图
        results = graph.query(sparql_query)
        for s, p, o in results:
            subgraph.add((s, p, o))
        
        # 收集第一度关系中的新实体
        new_entities = set()
        for s, p, o in subgraph.triples((None, None, None)):
            if isinstance(s, URIRef) and s not in entities:
                new_entities.add(s)
            if isinstance(o, URIRef) and o not in entities:
                new_entities.add(o)
        
        # 只有当有新实体时才执行第二个查询
        if new_entities:
            new_entity_values = ", ".join(f"<{e}>" for e in new_entities)
            # 同样使用占位符替换而非模板
            second_query_template = """
            CONSTRUCT { ?s ?p ?o }
            WHERE {
                { ?s ?p ?o . FILTER(?s IN (NEW_ENTITY_VALUES_PLACEHOLDER)) }
                UNION
                { ?s ?p ?o . FILTER(?o IN (NEW_ENTITY_VALUES_PLACEHOLDER)) }
            }
            """
            second_query = second_query_template.replace("NEW_ENTITY_VALUES_PLACEHOLDER", new_entity_values)
            
            results = graph.query(second_query)
            for s, p, o in results:
                subgraph.add((s, p, o))
        
        return subgraph

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

    async def query(self, text: str, user_id: str = None, limit: int = 5) -> str:
        """根据文本查询Turtle表达式"""
        user_id = user_id or "default"
        limit = int(limit / 2)
        limit = 1 if limit <= 0 else limit
        sub_graph, part_graph = await self._query_vector_db(text, user_id, limit)
        def _ex(s, p, o):
            return f"({self._extract_local_name(s)} {self._extract_local_name(p)} {self._extract_local_name(o)})"
        triples = [_ex(s, p, o) for s, p, o in part_graph]
        for s, p, o in sub_graph:
            triple = _ex(s, p, o)
            if triple not in triples:
                triples.append(triple)
        return "\n".join(triples[:limit])

    async def extract(self, text: str, user_id: str = None, limit: int = 5) -> Graph:
        """从文本生成知识并添加到图谱"""
        user_id = user_id or "default"

        _, part_graph = await self._query_vector_db(text, user_id, limit)
        existing_turtles = part_graph.serialize(format="turtle")

        turtle = await self.generate_turtle(
            content=text,
            user_id=user_id,
            existing_turtles=existing_turtles
        )
        self._logger.debug(f"raw_turtle: \n{turtle}")

        if not turtle:
            self._logger.warning(f"[{user_id}] 空的Turtle表达式")
            return ""

        # 解析并合并到图谱
        try:
            # 更新图谱
            self.graph.parse(data=turtle, format="turtle")

            # 保存到数据库
            await self._save_to_docs_db(turtle, user_id)
            # 保存到向量数据库
            await self._save_to_vector_db(turtle, user_id)

        except Exception as e:
            raise Exception(f"解析Turtle数据时出错: {e}")

        return turtle
    
    async def generate_turtle(self, content: str, existing_turtles: str = None, user_id: str = None) -> str:
        """使用大模型生成Turtle表达式"""
        user_id = user_id or "default"
        if not self.llm:
            # 如果没有提供大模型，返回空字符串
            return ""
        
        system_prompt = self.prompt_template.format({
            "namespacePrefix": f"http://illufly.com/{user_id}/memory#",
            "namespaceURI": "m",
            "content": content,
            "existing_turtles": existing_turtles or ""
        })

        turtles = []
        async for x in self.llm.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请开始生成Turtle表达式"}
        ]):
            if x.block_type == BlockType.TEXT_FINAL:
                self._logger.debug(f"TEXT_FINAL: \n{x.text}")
                turtles.extend(extract_segments(x.text, ("```turtle", "```")))
        return "\n".join(turtles)

    async def _save_to_docs_db(self, turtle: str, user_id: str = None) -> None:
        """将四元组文本保存到rocksdb"""
        user_id = user_id or "default"
        if not self.docs_db:
            return
        
        turtle = Turtle(
            user_id=user_id,
            turtle_text=turtle
        )
        self.docs_db.put(key=Turtle.get_key(user_id, turtle.turtle_id), value=turtle)
    
    async def init(self, user_id: str = None) -> Graph:
        """从rocksdb中加载Turtle表达式"""
        user_id = user_id or "default"

        if self.docs_db:
            for doc in self.docs_db.values(prefix=Turtle.get_user_prefix(user_id)):
                self._logger.debug(f"[{doc.turtle_id}] {doc.turtle_text}")
                self.graph.parse(data=doc.turtle_text, format="turtle")
                await self._save_to_vector_db(doc.turtle_text, user_id)
        self._logger.info(f"[{len(self.graph)}] 条知识已加载")

    async def _save_to_vector_db(self, turtle: str, user_id: str = None) -> None:
        """将图谱中的Turtle表达式保存到向量数据库"""
        user_id = user_id or "default"
        if not self.vector_db:
            return
        
        turtle_texts = self.split_turtle(turtle)
        texts = []
        metadatas = []
        ids = []
        for turtle_text, comment in turtle_texts:
            turtle_id = md5(turtle_text.encode()).hexdigest() # 生成 MD5 的 ID
            texts.append(f'{comment}\n{turtle_text}') # 将 turtle_text 和 comment 一起嵌入
            metadatas.append({"turtle": turtle_text}) # 只保存 turtle_text
            ids.append(f'{user_id}:{turtle_id}') # 保存向量嵌入 ID
            self._logger.info(f"[{user_id}:{turtle_id}] 加载到向量数据库 turtle_text: \n{turtle_text}")

        if texts:
            await self.vector_db.add(
                texts=texts,
                collection_name=user_id,
                metadatas=metadatas,
                ids=ids
            )
        else:
            self._logger.warning(f"[{user_id}] 没有可保存的文本")

    async def _query_vector_db(self, texts: Union[str, List[str]], user_id: str = None, limit: int = 5, distance: float = 0.8) -> Tuple[Graph, Graph]:
        """根据文本查询相关知识
        
        Args:
            user_id: 用户ID
            text: 查询文本
            
        Returns:
            格式化的知识文本
        """
        user_id = user_id or "default"
        results = await self.vector_db.query(
            texts=texts,
            collection_name=user_id,
            n_results=limit
        )
        turtle = ""
        part_graph = Graph()
        if results['metadatas']:
            for i in range(len(results['metadatas'][0])):
                if results['distances'][0][i] <= distance:
                    turtle += results['metadatas'][0][i]['turtle']
                    part_graph.parse(data=results['metadatas'][0][i]['turtle'], format="turtle")
        subgraph = self.extract_related_subgraph_sparql(self.graph, part_graph)
        return (self.get_newest_triples(subgraph), part_graph)

