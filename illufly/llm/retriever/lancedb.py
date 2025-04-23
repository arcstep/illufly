from typing import List, Any, Dict, Union, Optional, Set
import os
import asyncio
import logging
import hashlib
import numpy as np
import pandas as pd
import lancedb
import pyarrow as pa
import json
import time
import re

from .base import BaseRetriever
from lancedb.embeddings import EmbeddingFunctionRegistry
from ..litellm import LiteLLM

logger = logging.getLogger(__name__)

class LanceRetriever(BaseRetriever):
    """基于LanceDB的向量检索器 - 遵循LanceDB最佳实践"""
    
    def __init__(
        self, 
        output_dir: str = None, 
        embedding_config: Dict[str, Any] = {},
        vector_dim: int = 384
    ):
        """初始化LanceRetriever
        
        Args:
            output_dir: 数据库存储路径，默认为./lance_db
            embedding_config: 嵌入模型配置
            vector_dim: 向量维度，默认384
        """
        self.model = LiteLLM(model_type="embedding", **embedding_config)
        self.vector_dim = vector_dim
        
        # 设置数据库路径
        self.db_path = output_dir or "./lance_db"
        os.makedirs(self.db_path, exist_ok=True)
        
        # 初始化数据库连接
        self.db = lancedb.connect(self.db_path)
        self._logger = logging.getLogger(__name__)
    
    def _get_or_create_table(self, table_name: str) -> Any:
        """获取或创建表，延迟创建索引"""
        # 检查表是否存在
        if table_name in self.db.table_names():
            return self.db.open_table(table_name)
        
        # 创建表结构
        data = [{
            "vector": np.zeros(self.vector_dim, dtype=np.float32),
            "text": "",
            "user_id": "",
            "file_id": "",
            "chunk_index": 0,
            "original_name": "",
            "source_type": "",
            "source_url": "",
            "created_at": 0,
            "metadata_json": "{}"
        }]
        
        # 创建表，但不立即创建索引
        table = self.db.create_table(table_name, data=data)
        
        # 删除示例数据
        table.delete("text = ''")
        
        self._logger.info(f"创建新表: {table_name}")
        return table
    
    async def _get_embeddings(self, texts: Union[str, List[str]], **kwargs) -> List[List[float]]:
        """获取文本的嵌入向量 - 增强错误恢复能力"""
        if isinstance(texts, str):
            texts = [texts]
        
        all_embeddings = []
        
        for i, text in enumerate(texts):
            try:
                # 预处理文本，移除可能导致问题的重复模式
                orig_len = len(text)
                
                # 记录前100个字符，避免日志过大
                text_preview = text[:100] + "..." if len(text) > 100 else text
                self._logger.info(f"[文本{i+1}] 处理文本(长度:{len(text)}): {text_preview}")
                
                # 清理重复模式
                if ", = ." in text and text.count(", = .") > 10:
                    cleaned_text = re.sub(r'(, = \.){3,}', ' [...] ', text)
                    text = cleaned_text
                    self._logger.info(f"[文本{i+1}] 清理了重复模式，清理后长度: {len(text)}")
                
                # 清理多种可能的问题模式
                if len(text) > 1000:  # 只对较长文本执行昂贵的清理
                    # 1. 清理重复模式
                    text = re.sub(r'(, = \.){2,}', ' [...] ', text)
                    # 2. 清理连续重复的标点符号
                    text = re.sub(r'([,.;:!?]){3,}', r'\1\1', text)
                    # 3. 清理异常的空白字符序列
                    text = re.sub(r'\s{3,}', ' ', text)
                    # 4. 如果文本仍然很长，可能需要截断
                    if len(text) > 5000:
                        text = text[:5000] + "..."
                    
                    if len(text) != orig_len:
                        self._logger.info(f"[文本{i+1}] 清理了问题文本，原长度: {orig_len}, 现长度: {len(text)}")
                
                # 对于确实有问题的文本，我们尝试直接捕获嵌入错误并使用零向量，
                # 而不是让异常传播到更上层
                try:
                    # 调用嵌入API
                    resp = await self.model.aembedding(text, **kwargs)
                    
                    # 成功获取响应，尝试提取向量
                    if hasattr(resp, 'data') and isinstance(resp.data, list) and len(resp.data) > 0:
                        if isinstance(resp.data[0], dict) and 'embedding' in resp.data[0]:
                            embedding = resp.data[0]['embedding']
                            self._logger.info(f"[文本{i+1}] 成功获取向量，维度: {len(embedding)}, 前几个元素: {embedding[:5]}")
                        else:
                            raise ValueError("响应中没有正确的embedding")
                    else:
                        raise ValueError("响应结构不符合预期")
                    
                except Exception as e:
                    error_message = str(e)[:200] + "..." if len(str(e)) > 200 else str(e)
                    self._logger.error(f"[文本{i+1}] 获取嵌入向量失败: {error_message}")
                    
                    # 记录更详细的失败文本特征
                    char_types = {}
                    for c in text[:500]:  # 分析前500个字符
                        if c not in char_types:
                            char_types[c] = 0
                        char_types[c] += 1
                    
                    most_common = sorted([(c, count) for c, count in char_types.items()], key=lambda x: x[1], reverse=True)[:10]
                    self._logger.warning(f"[文本{i+1}] 失败文本特征 - 最常见字符: {most_common}")
                    
                    # 分析是否有特殊模式
                    special_patterns = {
                        ", = .": text.count(", = ."),
                        "=": text.count("="),
                        ",": text.count(","),
                        ".": text.count(".")
                    }
                    self._logger.warning(f"[文本{i+1}] 失败文本特征 - 特殊模式统计: {special_patterns}")
                    
                    # 对于失败的情况，我们尝试拆分文本再处理
                    if len(text) > 1000:
                        # 拆分成多个较小段落
                        chunks = []
                        words = text.split()
                        chunk_size = 200  # 每个小段落约200个单词
                        
                        for j in range(0, len(words), chunk_size):
                            chunk = " ".join(words[j:j+chunk_size])
                            chunks.append(chunk)
                        
                        self._logger.info(f"[文本{i+1}] 已拆分为{len(chunks)}个小段")
                        
                        # 对每个小段独立获取嵌入
                        chunk_embeddings = []
                        for j, chunk in enumerate(chunks):
                            try:
                                chunk_resp = await self.model.aembedding(chunk, **kwargs)
                                if hasattr(chunk_resp, 'data') and len(chunk_resp.data) > 0:
                                    chunk_emb = chunk_resp.data[0]['embedding']
                                    chunk_embeddings.append(chunk_emb)
                                    self._logger.info(f"[文本{i+1}.{j+1}] 小段嵌入成功")
                                else:
                                    self._logger.warning(f"[文本{i+1}.{j+1}] 小段嵌入结构异常")
                                    chunk_embeddings.append([0.0] * self.vector_dim)
                            except:
                                self._logger.warning(f"[文本{i+1}.{j+1}] 小段嵌入失败")
                                chunk_embeddings.append([0.0] * self.vector_dim)
                        
                        # 如果有成功的小段嵌入，取它们的平均值
                        if chunk_embeddings:
                            embeddings_array = np.array(chunk_embeddings)
                            embedding = np.mean(embeddings_array, axis=0).tolist()
                            self._logger.info(f"[文本{i+1}] 使用{len(chunk_embeddings)}个小段的平均嵌入")
                        else:
                            embedding = [0.0] * self.vector_dim
                    else:
                        # 对于短文本，直接使用零向量
                        self._logger.warning(f"[文本{i+1}] 无法生成嵌入")
                        embedding = [0.0] * self.vector_dim
                
                # 确保维度正确
                if len(embedding) != self.vector_dim:
                    if len(embedding) < self.vector_dim:
                        embedding = embedding + [0.0] * (self.vector_dim - len(embedding))
                    else:
                        embedding = embedding[:self.vector_dim]
                
                all_embeddings.append(embedding)
            except Exception as e:
                # 最外层异常捕获
                self._logger.error(f"[文本{i+1}] 处理文本完全失败: {type(e).__name__} - {str(e)[:100]}")
                all_embeddings.append([0.0] * self.vector_dim)
        
        return all_embeddings
    
    async def add(
        self,
        texts: Union[str, List[str]],
        collection_name: str = None,
        user_id: str = None,
        metadatas: Union[Dict[str, Any], List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """添加文本到向量库，自动处理长文本和格式化元数据
        
        Args:
            texts: 文本内容，单个字符串或字符串列表
            collection_name: 集合名称，默认为"documents"
            user_id: 用户ID，默认为"default"
            metadatas: 元数据，单个字典或字典列表
            **kwargs: 传递给嵌入模型的额外参数
            
        Returns:
            添加结果统计
        """
        # 标准化参数
        if isinstance(texts, str):
            texts = [texts]
        
        table_name = collection_name or "documents"
        user_id = user_id or "default"
        
        # 标准化元数据
        if metadatas is None:
            metadatas = [{} for _ in texts]
        elif isinstance(metadatas, dict):
            metadatas = [metadatas] * len(texts)
        
        if len(metadatas) != len(texts):
            raise ValueError(f"元数据长度({len(metadatas)})与文本长度({len(texts)})不匹配")
        
        # 处理长文本分段
        max_tokens = 500  # 安全上限，小于模型限制
        final_texts = []
        final_metadatas = []
        
        for text, metadata in zip(texts, metadatas):
            # 估计token数量(简单估计：按空格分词，每个单词平均算1.3个token)
            est_tokens = len(text.split()) * 1.3
            
            if est_tokens > max_tokens:
                # 分段处理
                words = text.split()
                max_words = int(max_tokens / 1.3)  # 转换回单词数
                
                # 创建文本段
                segments = []
                for i in range(0, len(words), max_words):
                    segment = " ".join(words[i:i+max_words])
                    segments.append(segment)
                
                # 为每个段创建元数据
                for i, segment in enumerate(segments):
                    segment_metadata = metadata.copy()
                    # 添加分段信息
                    segment_metadata.update({
                        "segment_index": i,
                        "total_segments": len(segments),
                        "is_segmented": True
                    })
                    final_texts.append(segment)
                    final_metadatas.append(segment_metadata)
            else:
                # 不需要分段
                final_texts.append(text)
                final_metadatas.append(metadata)
        
        # 获取表
        table = self._get_or_create_table(table_name)
        
        # 获取嵌入向量
        self._logger.info(f"处理后的文本数量: {len(final_texts)}，原始文本数量: {len(texts)}")
        embeddings = await self._get_embeddings(final_texts, **kwargs)
        
        # 准备数据 - 只保留成功获取到非零向量的记录
        records = []
        skipped_count = 0
        timestamp = int(time.time())
        
        for text, embedding, metadata in zip(final_texts, embeddings, final_metadatas):
            # 检查是否为零向量（嵌入失败的情况）
            if all(v == 0.0 for v in embedding[:10]):  # 检查前10个元素是否都为0
                skipped_count += 1
                self._logger.info(f"跳过零向量文本，不入库: {text[:50]}...")
                continue  # 跳过此记录
            
            # 提取常用元数据
            file_id = metadata.get("file_id", "")
            chunk_index = metadata.get("chunk_index", 0)
            original_name = metadata.get("original_name", "")
            source_type = metadata.get("source_type", "")
            source_url = metadata.get("source_url", "")
            
            # 其他元数据序列化为JSON
            extra_metadata = {k: v for k, v in metadata.items() 
                             if k not in ["file_id", "chunk_index", "original_name", 
                                         "source_type", "source_url"]}
            
            # 创建记录
            record = {
                "vector": np.array(embedding, dtype=np.float32),
                "text": text,
                "user_id": user_id,
                "file_id": file_id,
                "chunk_index": chunk_index,
                "original_name": original_name,
                "source_type": source_type,
                "source_url": source_url,
                "created_at": timestamp,
                "metadata_json": json.dumps(extra_metadata)
            }
            records.append(record)
        
        # 添加到数据库
        try:
            if records:  # 只有在有成功记录时才添加
                table.add(records)
            return {
                "success": True, 
                "added": len(records), 
                "skipped": skipped_count,
                "original_count": len(texts)
            }
        except Exception as e:
            self._logger.error(f"添加记录失败: {str(e)}")
            return {"success": False, "added": 0, "skipped": skipped_count, "error": str(e)}
    
    async def delete(
        self,
        collection_name: str = None,
        user_id: str = None,
        file_id: str = None,
        filter: str = None
    ) -> Dict[str, Any]:
        """删除向量数据
        
        Args:
            collection_name: 集合名称，默认为"documents"
            user_id: 按用户ID删除
            file_id: 按文件ID删除
            filter: 自定义过滤条件(SQL WHERE语句)
            
        Returns:
            删除结果统计
        """
        table_name = collection_name or "documents"
        
        # 检查表是否存在
        if table_name not in self.db.table_names():
            return {"success": True, "deleted": 0, "message": "表不存在"}
        
        table = self.db.open_table(table_name)
        
        # 构建过滤条件
        conditions = []
        if user_id:
            conditions.append(f"user_id = '{user_id}'")
        if file_id:
            conditions.append(f"file_id = '{file_id}'")
        if filter:
            conditions.append(f"({filter})")
        
        if not conditions:
            return {"success": False, "deleted": 0, "message": "未提供删除条件"}
        
        where_clause = " AND ".join(conditions)
        
        try:
            # 执行删除
            table.delete(where_clause)
            return {"success": True, "deleted": 1, "message": "删除成功"}
        except Exception as e:
            self._logger.error(f"删除数据失败: {str(e)}")
            return {"success": False, "deleted": 0, "error": str(e)}
    
    async def query(
        self,
        query_texts: Union[str, List[str]],
        collection_name: str = None,
        user_id: str = None,
        file_id: str = None,
        limit: int = 10,
        threshold: float = 0.7,
        filter: str = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """向量检索
        
        Args:
            query_texts: 查询文本，字符串或字符串列表
            collection_name: 集合名称，默认为"documents"
            user_id: 按用户ID过滤
            file_id: 按文件ID过滤
            limit: 返回结果数量限制
            threshold: 相似度阈值(越低表示越相似)
            filter: 自定义过滤条件(SQL WHERE语句)
            **kwargs: 传递给嵌入模型的额外参数
            
        Returns:
            检索结果列表
        """
        if isinstance(query_texts, str):
            query_texts = [query_texts]
            
        table_name = collection_name or "documents"
        
        # 检查表是否存在
        if table_name not in self.db.table_names():
            return [{
                "query": text,
                "results": []
            } for text in query_texts]
        
        table = self.db.open_table(table_name)
        
        # 构建过滤条件
        conditions = []
        if user_id:
            conditions.append(f"user_id = '{user_id}'")
        if file_id:
            conditions.append(f"file_id = '{file_id}'")
        if filter:
            conditions.append(f"({filter})")
        
        where_clause = " AND ".join(conditions) if conditions else None
        
        # 获取查询向量
        query_embeddings = await self._get_embeddings(query_texts, **kwargs)
        
        # 执行查询
        results = []
        
        for i, (query_text, query_embedding) in enumerate(zip(query_texts, query_embeddings)):
            try:
                # 创建查询构建器
                search = table.search(query_embedding)
                
                # 添加过滤条件
                if where_clause:
                    search = search.where(where_clause)
                
                # 设置返回数量限制
                search = search.limit(limit)
                
                # 执行查询
                df = search.to_pandas()
                
                # 过滤相似度
                if len(df) > 0:
                    df = df[df['_distance'] < threshold]
                
                # 格式化结果
                matches = []
                
                for _, row in df.iterrows():
                    # 解析额外元数据
                    try:
                        extra_metadata = json.loads(row.get('metadata_json', '{}'))
                    except:
                        extra_metadata = {}
                    
                    # 构建基本元数据
                    metadata = {
                        "user_id": row.get('user_id', ''),
                        "file_id": row.get('file_id', ''),
                        "chunk_index": row.get('chunk_index', 0),
                        "original_name": row.get('original_name', ''),
                        "source_type": row.get('source_type', ''),
                        "source_url": row.get('source_url', '')
                    }
                    
                    # 合并额外元数据
                    metadata.update(extra_metadata)
                    
                    # 添加匹配项
                    matches.append({
                        "text": row['text'],
                        "score": float(row['_distance']),
                        "metadata": metadata
                    })
                
                # 添加到结果
                results.append({
                    "query": query_text,
                    "results": matches
                })
                
            except Exception as e:
                self._logger.error(f"查询失败: {str(e)}")
                results.append({
                    "query": query_text,
                    "results": [],
                    "error": str(e)
                })
        
        return results
    
    async def list_collections(self) -> List[str]:
        """列出所有集合名称"""
        table_names = self.db.table_names()
        # 表名前缀是'vectors_'，需要去掉
        collections = [name[8:] for name in table_names if name.startswith('vectors_')]
        return collections
    
    async def get_stats(self, collection_name: str = None) -> Dict[str, Any]:
        """获取集合统计信息
        
        Args:
            collection_name: 集合名称，为None时返回所有集合的统计信息
            
        Returns:
            统计信息字典
        """
        stats = {}
        
        if collection_name is not None:
            # 统计单个集合
            try:
                table = self._get_or_create_table(collection_name)
                df = table.to_pandas()
                
                stats[collection_name] = {
                    "total_vectors": len(df),
                    "unique_users": df['user_id'].nunique(),
                    "unique_files": df['file_id'].nunique(),
                }
            except Exception as e:
                self._logger.error(f"获取集合统计信息失败: {str(e)}")
                stats[collection_name] = {"error": str(e)}
        else:
            # 统计所有集合
            collections = await self.list_collections()
            for coll in collections:
                coll_stats = await self.get_stats(coll)
                stats.update(coll_stats)
        
        return stats

    async def ensure_index(self, collection_name: str = None):
        """确保表有索引 - 当数据量足够时才创建索引"""
        table_name = collection_name or "documents"
        if table_name not in self.db.table_names():
            return False
        
        table = self.db.open_table(table_name)
        
        # 检查表中的行数
        count_df = table.to_pandas()
        row_count = len(count_df)
        
        # 只有当数据量足够大时才创建索引
        if row_count >= 100:  # 开发环境使用较小阈值
            try:
                # 尝试创建索引
                self._logger.info(f"为表 {table_name} 创建向量索引，当前数据量: {row_count}")
                await table.create_index(vector_column_name="vector", metric="cosine")
                return True
            except Exception as e:
                self._logger.warning(f"创建索引失败: {str(e)}")
                return False
        else:
            self._logger.info(f"表 {table_name} 数据量({row_count})不足，暂不创建索引")
            return False
    
    async def close(self):
        """关闭LanceDB连接和清理资源
        
        优雅关闭数据库连接，释放所有资源
        """
        try:
            # 关闭嵌入模型资源
            if hasattr(self, 'model') and hasattr(self.model, 'close'):
                self._logger.info("关闭嵌入模型资源...")
                await self.model.close()
            
            # 关闭LanceDB连接
            if hasattr(self, 'db'):
                self._logger.info("关闭LanceDB连接...")
                
                # 尝试关闭所有打开的表
                if hasattr(self.db, 'table_names') and callable(self.db.table_names):
                    try:
                        for table_name in self.db.table_names():
                            self._logger.info(f"明确关闭表: {table_name}")
                            # 显式释放表资源
                            table = self.db.open_table(table_name)
                            if hasattr(table, 'close') and callable(table.close):
                                table.close()
                            del table
                    except Exception as e:
                        self._logger.error(f"关闭表时出错: {str(e)}")
                
                # 关闭数据库对象
                if hasattr(self.db, 'close') and callable(self.db.close):
                    self.db.close()
                
                # 强制删除引用
                self.db = None
                
                # 尝试调用垃圾回收
                import gc
                gc.collect()
            
            self._logger.info("向量检索器资源已释放")
            return True
        except Exception as e:
            self._logger.error(f"关闭向量检索器时出错: {str(e)}")
            return False
