from typing import Dict, Any, Optional, List
from pathlib import Path
import aiofiles
import logging
import base64
from fastapi import UploadFile
from voidrail import CeleryClient
from .chunker import get_chunker
from ..llm import LanceRetriever

CONVERT_SERVICE_NAME = "docling"
CONVERT_METHOD_NAME = "convert"

class MarkdownProcessor:
    """Markdown文档处理器 - 专注于文档的转换、切片和向量化
    
    主要功能：
    1. 文件处理
       - 上传文件并转换为Markdown
       - 注册远程URL并转换为Markdown
       - 处理文件大小和类型限制
    
    2. 文档处理
       - 使用chunker进行文档切片
       - 生成文档向量嵌入
       - 管理向量存储
    
    3. 资源管理
       - 临时文件管理
       - 向量存储管理
       - 错误处理和日志
    """
    
    def __init__(
        self,
        temp_dir: str,
        vector_db_path: str = None,
        embedding_config: Dict[str, Any] = {},
        max_file_size: int = 50 * 1024 * 1024,
        allowed_extensions: List[str] = None,
        logger = None
    ):
        """初始化处理器
        
        Args:
            temp_dir: 临时文件目录
            vector_db_path: 向量数据库路径
            embedding_config: 嵌入模型配置
            max_file_size: 最大文件大小限制
            allowed_extensions: 允许的文件扩展名列表
            logger: 日志记录器
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max_file_size
        self.allowed_extensions = allowed_extensions or [
            '.pptx', '.md', '.markdown', '.pdf', '.docx', '.txt',
            '.jpg', '.jpeg', '.png', '.gif', '.webp'
        ]
        self.logger = logger or logging.getLogger(__name__)
        
        # 初始化转换服务客户端
        self.voidrail_client = CeleryClient(CONVERT_SERVICE_NAME)
        
        # 初始化向量检索器
        if vector_db_path:
            self.retriever = LanceRetriever(
                output_dir=vector_db_path,
                embedding_config=embedding_config,
                metric="cosine"
            )
        else:
            self.retriever = None
    
    def is_valid_file_type(self, file_name: str) -> bool:
        """检查文件类型是否有效"""
        _, ext = os.path.splitext(file_name)
        return ext.lower() in self.allowed_extensions
    
    async def _convert_to_markdown(
        self,
        content: str,
        content_type: str,
        file_type: str
    ) -> Dict[str, Any]:
        """内部方法：将内容转换为Markdown格式"""
        try:
            # 准备转换参数
            conversion_params = {
                "file_type": file_type,
                "output_format": "markdown",
                "content": content,
                "content_type": content_type
            }
            
            # 使用LLM服务转换
            markdown_content = ""
            async for chunk in self.voidrail_client.stream(
                f"{CONVERT_SERVICE_NAME}.{CONVERT_METHOD_NAME}",
                **conversion_params
            ):
                markdown_content += chunk
            
            return {
                "content": markdown_content,
                "success": True
            }
        except Exception as e:
            self.logger.error(f"转换Markdown失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_upload(
        self,
        file: UploadFile,
        user_id: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """处理上传的文件：保存到临时目录并转换为Markdown
        
        Args:
            file: 上传的文件
            user_id: 用户ID
            metadata: 文档元数据
            
        Returns:
            处理结果，包含文档内容和元数据
        """
        try:
            # 1. 检查文件类型
            if not self.is_valid_file_type(file.filename):
                raise ValueError(f"不支持的文件类型: {file.filename}")
            
            # 2. 保存到临时目录
            temp_path = self.temp_dir / f"{user_id}_{file.filename}"
            file_size = 0
            async with aiofiles.open(temp_path, 'wb') as f:
                while content := await file.read(1024 * 1024):  # 每次读取1MB
                    file_size += len(content)
                    if file_size > self.max_file_size:
                        await f.close()
                        temp_path.unlink()
                        raise ValueError(f"文件大小超过限制: {self.max_file_size} bytes")
                    await f.write(content)
            
            try:
                # 3. 读取文件内容并转换为base64
                async with aiofiles.open(temp_path, 'rb') as f:
                    file_content = await f.read()
                    base64_content = base64.b64encode(file_content).decode('utf-8')
                
                # 4. 转换为Markdown
                file_type = os.path.splitext(file.filename)[1][1:]  # 去掉点号
                result = await self._convert_to_markdown(
                    base64_content,
                    "base64",
                    file_type
                )
                
                if not result["success"]:
                    raise ValueError(f"转换失败: {result.get('error')}")
                
                return {
                    "success": True,
                    "content": result["content"],
                    "metadata": {
                        **(metadata or {}),
                        "original_name": file.filename,
                        "size": file_size,
                        "type": file_type
                    }
                }
            finally:
                # 5. 清理临时文件
                if temp_path.exists():
                    temp_path.unlink()
                    
        except Exception as e:
            self.logger.error(f"处理上传文件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_url(
        self,
        url: str,
        user_id: str,
        filename: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """处理远程文件：下载并转换为Markdown
        
        Args:
            url: 远程文件URL
            user_id: 用户ID
            filename: 文件名
            metadata: 文档元数据
            
        Returns:
            处理结果，包含文档内容和元数据
        """
        try:
            # 1. 检查文件类型
            if not self.is_valid_file_type(filename):
                raise ValueError(f"不支持的文件类型: {filename}")
            
            # 2. 转换为Markdown
            file_type = os.path.splitext(filename)[1][1:]  # 去掉点号
            result = await self._convert_to_markdown(
                url,
                "url",
                file_type
            )
            
            if not result["success"]:
                raise ValueError(f"转换失败: {result.get('error')}")
            
            return {
                "success": True,
                "content": result["content"],
                "metadata": {
                    **(metadata or {}),
                    "original_name": filename,
                    "source_type": "remote",
                    "source_url": url,
                    "type": file_type
                }
            }
        except Exception as e:
            self.logger.error(f"处理远程文件失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_embedding(
        self,
        document_id: str,
        content: str,
        user_id: str,
        metadata: Dict[str, Any] = None,
        collection_name: str = None
    ) -> Dict[str, Any]:
        """处理文档：切片和向量化
        
        Args:
            document_id: 文档ID
            content: Markdown内容
            user_id: 用户ID
            metadata: 文档元数据
            collection_name: 向量集合名称
            
        Returns:
            处理结果，包含切片和向量化信息
        """
        try:
            if not self.retriever:
                raise ValueError("未配置向量检索器")
            
            # 1. 使用chunker进行切片
            chunker = get_chunker("markdown")
            chunks = await chunker.chunk_document(content, metadata)
            
            if not chunks:
                raise ValueError("文档切片结果为空")
            
            # 2. 准备向量元数据
            vector_metadata = []
            for i, chunk in enumerate(chunks):
                chunk_meta = {
                    "document_id": document_id,
                    "chunk_index": i,
                    "user_id": user_id,
                    **(metadata or {})
                }
                vector_metadata.append(chunk_meta)
            
            # 3. 添加向量
            result = await self.retriever.add(
                collection_name or f"user_{user_id}",
                texts=[chunk["content"] for chunk in chunks],
                metadatas=vector_metadata,
                ids=[f"{document_id}_{i}" for i in range(len(chunks))]
            )
            
            if not result.get("success", False):
                raise ValueError(f"向量添加失败: {result.get('error', '未知错误')}")
            
            # 4. 确保创建索引
            await self.retriever.ensure_index(collection_name or f"user_{user_id}")
            
            return {
                "success": True,
                "chunks": chunks,
                "vectors_count": len(chunks),
                "collection": collection_name or f"user_{user_id}"
            }
        except Exception as e:
            self.logger.error(f"处理文档嵌入失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def remove_embedding(
        self,
        user_id: str,
        document_id: str,
        collection_name: str = None
    ) -> bool:
        """从向量存储中删除文档的嵌入向量
        
        Args:
            user_id: 用户ID
            document_id: 文档ID
            collection_name: 向量集合名称
            
        Returns:
            是否成功删除
        """
        if not self.retriever:
            return False
        
        try:
            result = await self.retriever.delete(
                collection_name or f"user_{user_id}",
                user_id=user_id,
                document_id=document_id
            )
            return result.get("success", False)
        except Exception as e:
            self.logger.error(f"删除向量嵌入失败: {e}")
            return False
