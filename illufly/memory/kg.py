from typing import Dict, List, Tuple, Optional, Any, Set, Union
from rdflib import Graph, Namespace, Literal, URIRef, BNode
from rdflib.namespace import RDF, RDFS

import uuid
import logging

from ..community import BaseVectorDB, BaseChat
from ..rocksdb import IndexedRocksDB, default_rocksdb
from ..prompt import PromptTemplate

class KnowledgeGraph:
    """RDF知识图谱包装类
    
    管理用户的知识图谱，支持从文本生成图谱、解决冲突和查询相关知识
    """
    
    def __init__(
        self,
        llm: Optional[BaseChat] = None,
        vector_db: Optional[BaseVectorDB] = None,
        docs_db: Optional[IndexedRocksDB] = None,
        prompt_template: Optional[PromptTemplate] = None
    ):
        """初始化知识图谱"""
        self.docs_db = docs_db or default_rocksdb
        self.vector_db = vector_db
        self.llm = llm
        self.prompt_template = prompt_template or PromptTemplate(template_id="turtle-nl")
        self._logger = logging.getLogger(__name__)
        
        self.graph = Graph()
        
        # 定义标准命名空间
        self.namespaces = {
            "ex": Namespace("http://example.org/"),
            "rdfs": Namespace("http://www.w3.org/2000/01/rdf-schema#"),
            "rdf": RDF,
        }
        
        # 绑定命名空间到图谱
        for prefix, ns in self.namespaces.items():
            self.graph.bind(prefix, ns)
    
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
        turtle_data = await self._generate_turtle(prompt=text, existing_turtles=existing_turtles)
        
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

    async def _generate_turtle(self, prompt: str, existing_turtles: str) -> str:
        """使用大模型生成Turtle表达式"""
        if not self.llm:
            # 如果没有提供大模型，返回空字符串
            return ""
        
        system_prompt = self.prompt_template.format({
            "namespacePrefix": "https://illufly.com",
            "namespaceURI": "illufly",
            "content": prompt,
            "existing_turtles": existing_turtles
        })
        final_text = ""
        async for x in self.llm.generate([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请开始"}
        ]):
            if x.message_type == "text_chunk":
                final_text += x.text
        return final_text.replace("```turtle\n", "").replace("\n```", "").strip()
    
    async def _resolve_conflicts(self, new_graph: Graph) -> None:
        """解决图谱合并时的概念冲突"""
        # 获取所有主语
        subjects = set()
        for s, _, _ in new_graph:
            subjects.add(s)
        
        for subject in subjects:
            # 处理每个主语的所有三元组
            for _, predicate, _ in new_graph.triples((subject, None, None)):
                # 检查是否存在冲突（同一主语和谓语，但宾语不同）
                existing_objects = set(self.graph.objects(subject, predicate))
                new_objects = set(new_graph.objects(subject, predicate))
                
                if existing_objects and existing_objects != new_objects:
                    # 冲突解决策略: 对于非标签和注释属性，保留新值
                    # 对于标签和注释，保留所有值
                    if predicate in (RDFS.label, RDFS.comment):
                        # 保留所有标签和注释
                        pass
                    else:
                        # 移除旧值，之后添加新值
                        for obj in existing_objects:
                            self.graph.remove((subject, predicate, obj))
            
            # 添加新三元组
            for s, p, o in new_graph.triples((subject, None, None)):
                self.graph.add((s, p, o))
    
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
    

