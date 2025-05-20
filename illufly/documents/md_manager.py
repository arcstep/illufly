import re
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from .md_indexing import MarkdownIndexing
from .path_manager import PathManager

class MarkdownManager:
    """Markdown文档管理器 - 处理文档内容、元数据、主题结构和索引
    
    业务逻辑说明：
    1. 文档管理
       - 文档以Markdown格式存储，使用frontmatter管理元数据
       - 每个文档有唯一ID（UUID格式），文件名格式为 `__id_{document_id}__.md`
       - 文档存储在用户目录下的主题目录中，支持多级主题结构
       - 文档元数据包含：标题、创建时间、更新时间、文档ID、主题路径等
    
    2. 主题管理
       - 支持创建、删除、重命名、移动、复制和合并主题
       - 主题是目录结构，可以包含子主题和文档
       - 主题操作会自动更新相关文档的元数据和索引
       - 支持主题的递归操作（如删除主题时处理子主题）
    
    3. 索引管理
       - 维护文档ID到文件路径的映射关系
       - 支持文件系统变更后的索引修复
       - 提供缓存机制，可保存和加载索引状态
       - 支持增量更新和全量刷新索引
    
    4. 文件系统协调
       - 协调文件系统操作和索引更新
       - 处理文件直接移动等外部操作
       - 自动修复索引与文件系统的不一致
       - 支持文档引用（图片、其他文档）的路径解析
    
    5. 并发控制
       - 使用用户级别的锁确保并发安全
       - 支持异步操作，提高性能
       - 防止索引更新冲突
    
    主要功能：
    1. 文档操作
       - create_document: 创建新文档，自动生成ID和元数据
       - read_document: 读取文档内容和元数据，支持文件系统搜索
       - update_document: 更新文档内容或元数据
       - delete_document: 删除文档及其索引
       - move_document: 移动文档到新主题
    
    2. 主题操作
       - create_topic: 创建新主题目录
       - delete_topic: 删除主题及其文档
       - rename_topic: 重命名主题，更新相关文档
       - move_topic: 移动主题到新位置
       - copy_topic: 复制主题及其文档
       - merge_topics: 合并两个主题
    
    3. 索引管理
       - initialize: 初始化索引，扫描所有用户文档
       - save_cache/load_cache: 保存/加载索引缓存
       - verify_and_repair_document_paths: 验证和修复文档路径
    
    4. 引用处理
       - extract_references: 提取文档中的图片和文档引用
       - get_document_with_resources: 获取文档及其引用的资源
    
    使用场景：
    1. MD文档管理系统
       - 支持多用户、多主题的文档组织
       - 提供文档的增删改查操作
       - 维护文档的元数据和引用关系
    
    2. Topic管理
       - 支持灵活的主题结构调整
       - 自动处理文档的移动和更新
       - 保持文件系统和索引的一致性
    
    3. 磁盘缓存索引维护
       - 处理文件系统直接操作
       - 自动修复索引不一致
       - 提供缓存机制提高性能
    
    注意事项：
    1. 文件操作
       - 所有文件操作都是异步的
       - 文件路径使用相对路径存储
       - 支持文件系统直接操作后的修复
    
    2. 并发处理
       - 使用用户级锁确保并发安全
       - 支持异步操作提高性能
       - 防止索引更新冲突
    
    3. 错误处理
       - 所有操作都有错误日志
       - 支持自动修复常见问题
       - 保持数据一致性
    """
    
    def __init__(self, base_dir: str):
        """初始化Markdown管理器"""
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        
        # 创建辅助管理器 - 注意路径管理器只传递给索引管理器
        path_manager = PathManager(base_dir)
        self.index_manager = MarkdownIndexing(path_manager)
    
    async def initialize(self, callback=None):
        """初始化系统，构建文档索引"""
        return await self.index_manager.initialize(callback)
    
    async def save_cache(self, cache_file: str = None) -> bool:
        """保存索引缓存到文件"""
        return await self.index_manager.save_cache(cache_file)
    
    async def load_cache(self, cache_file: str = None) -> bool:
        """从文件加载索引缓存"""
        return await self.index_manager.load_cache(cache_file)
    
    async def create_document(self, user_id: str, topic_path: str, title: str, 
                              content: str = "", metadata: Dict[str, Any] = None) -> str:
        """创建新的 Markdown 文档
        
        Args:
            user_id: 用户ID
            topic_path: 主题路径
            title: 文档标题
            content: 文档内容
            metadata: 自定义元数据
            
        Returns:
            str: 成功返回文档ID，失败返回None
            
        Raises:
            DocumentIdConflictError: 当生成的文档ID与现有文档冲突时
        """
        # 1. 生成文档ID并检查是否已存在
        max_attempts = 3  # 最大尝试次数
        for _ in range(max_attempts):
            document_id = str(uuid.uuid4())
            # 检查ID是否已存在
            if not await self.index_manager.get_document_path(user_id, document_id):
                break
        else:
            self.logger.error(f"无法生成唯一的文档ID，已尝试 {max_attempts} 次")
            return None
        
        # 2. 准备元数据
        if metadata is None:
            metadata = {}
        
        now = datetime.now().isoformat()
        default_metadata = {
            "title": title,
            "created_at": now,
            "updated_at": now,
            "document_id": document_id,
            "topic_path": topic_path
        }
        
        # 合并用户提供的元数据
        for key, value in metadata.items():
            default_metadata[key] = value
        
        # 3. 通过索引管理器创建文档并更新索引
        try:
            success = await self.index_manager.create_document(
                user_id, 
                document_id, 
                topic_path, 
                title,
                content, 
                default_metadata
            )
            
            if success:
                return document_id
            return None
        except Exception as e:
            self.logger.error(f"创建文档失败: {document_id}, 错误: {e}")
            return None
    
    async def read_document(self, user_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        """读取文档内容和元数据"""
        return await self.index_manager.read_document_file(user_id, document_id)
    
    async def update_document(self, user_id: str, document_id: str, 
                              content: Optional[str] = None, 
                              metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新文档内容或元数据"""
        # 1. 读取当前文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return False
            
        # 2. 更新内容或元数据
        current_content = document["content"]
        current_metadata = document["metadata"]
        
        if content is not None:
            current_content = content
            
        if metadata is not None:
            # 更新元数据
            for key, value in metadata.items():
                current_metadata[key] = value
                
        # 始终更新修改时间
        current_metadata["updated_at"] = datetime.now().isoformat()
        
        # 3. 通过索引管理器更新文档
        return await self.index_manager.update_document_file(
            user_id, 
            document_id, 
            current_content, 
            current_metadata
        )
    
    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """删除文档"""
        return await self.index_manager.delete_document_file(user_id, document_id)
    
    def extract_references(self, content: str) -> Dict[str, List[str]]:
        """提取 Markdown 内容中的引用资源"""
        references = {
            "images": [],
            "links": []
        }
        
        # 提取图片链接: ![alt](url)
        image_pattern = r'!\[(.*?)\]\((.*?)\)'
        for match in re.finditer(image_pattern, content):
            image_url = match.group(2).strip()
            if image_url and not image_url.startswith(('http://', 'https://')):
                references["images"].append(image_url)
        
        # 提取普通链接: [text](url)
        link_pattern = r'(?<!!)\[(.*?)\]\((.*?)\)'
        for match in re.finditer(link_pattern, content):
            link_url = match.group(2).strip()
            if link_url and not link_url.startswith(('http://', 'https://')) and link_url.endswith('.md'):
                references["links"].append(link_url)
        
        return references
    
    async def get_document_with_resources(self, user_id: str, document_id: str, 
                                          resolve_references: bool = False) -> Optional[Dict[str, Any]]:
        """读取文档及其引用的资源"""
        # 读取基本文档
        document = await self.read_document(user_id, document_id)
        if not document:
            return None
        
        # 提取引用资源
        content = document["content"]
        topic_path = document["metadata"].get("topic_path", "")
        references = self.extract_references(content)
        
        # 处理相对路径
        base_dir = self.index_manager.get_topic_path(user_id, topic_path)
        
        # 解析图片路径
        resolved_images = []
        for img_path in references["images"]:
            full_path = (base_dir / img_path).resolve()
            if full_path.exists():
                resolved_images.append({
                    "path": img_path,
                    "exists": True,
                    "full_path": str(full_path)
                })
            else:
                resolved_images.append({
                    "path": img_path,
                    "exists": False
                })
        
        # 解析文档引用
        resolved_links = []
        if resolve_references:
            for link_path in references["links"]:
                # 检查是否为文档ID格式
                if link_path.startswith("__id_") and link_path.endswith("__.md"):
                    ref_doc_id = link_path[5:-5]
                    ref_doc = await self.read_document(user_id, ref_doc_id)
                    if ref_doc:
                        resolved_links.append({
                            "path": link_path,
                            "exists": True,
                            "document_id": ref_doc_id,
                            "title": ref_doc["metadata"].get("title", ""),
                            "content": ref_doc["content"] if resolve_references else None
                        })
                    else:
                        resolved_links.append({
                            "path": link_path,
                            "exists": False,
                            "document_id": ref_doc_id
                        })
                else:
                    # 常规相对路径
                    full_path = (base_dir / link_path).resolve()
                    if full_path.exists():
                        try:
                            with open(full_path, 'r', encoding='utf-8') as f:
                                linked_content = f.read()
                                
                            resolved_links.append({
                                "path": link_path,
                                "exists": True,
                                "full_path": str(full_path),
                                "content": linked_content if resolve_references else None
                            })
                        except Exception:
                            resolved_links.append({
                                "path": link_path,
                                "exists": True,
                                "full_path": str(full_path),
                                "error": "无法读取文件内容"
                            })
                    else:
                        resolved_links.append({
                            "path": link_path,
                            "exists": False
                        })
        
        # 组合结果
        result = {
            **document,
            "references": {
                "images": resolved_images,
                "links": resolved_links
            }
        }
        
        return result
        
    async def move_document(self, user_id: str, document_id: str, target_topic_path: str) -> bool:
        """将文档移动到另一个主题"""
        return await self.index_manager.move_document(user_id, document_id, target_topic_path)
    
    async def get_topic_structure(self, user_id: str, relative_path: str = "") -> Dict[str, Any]:
        """获取主题结构信息"""
        return await self.index_manager.get_topic_structure(user_id, relative_path)

    def list_all_topics(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户的所有主题"""
        return self._list_topics_recursive(user_id)

    def _list_topics_recursive(self, user_id: str, current_path: str = "") -> List[Dict[str, Any]]:
        """递归获取用户的所有主题信息"""
        topic_info = self.index_manager.get_topic_structure(user_id, current_path)
        result = [{
            "user_id": user_id,
            "path": current_path or "/",
            "document_count": len(topic_info["document_ids"]),
            "subtopic_count": len(topic_info["subtopics"])
        }]
        
        for subtopic in topic_info["subtopics"]:
            subtopic_path = f"{current_path}/{subtopic}".lstrip("/")
            sub_results = self._list_topics_recursive(user_id, subtopic_path)
            result.extend(sub_results)
        
        return result

    async def create_topic(self, user_id: str, relative_path: str) -> bool:
        """创建主题目录"""
        return await self.index_manager.create_topic(user_id, relative_path)

    async def delete_topic(self, user_id: str, relative_path: str, force: bool = False) -> bool:
        """删除主题目录，同步更新文档元数据"""
        if not relative_path:
            return False  # 禁止删除根目录
        
        if not force:
            # 检查是否有文档
            document_ids = self.index_manager.get_physical_document_ids(user_id, relative_path)
            if document_ids:
                return False  # 包含文档且不强制删除
        
        # 委托给索引管理器处理
        return await self.index_manager.delete_topic(user_id, relative_path)

    async def rename_topic(self, user_id: str, old_path: str, new_name: str) -> bool:
        """重命名主题目录，同步更新文档元数据"""
        return await self.index_manager.rename_topic_with_metadata(user_id, old_path, new_name)

    async def move_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """移动主题到新位置，同步更新文档元数据"""
        return await self.index_manager.move_topic_with_metadata(user_id, source_path, target_path)

    async def copy_topic(self, user_id: str, source_path: str, target_path: str) -> bool:
        """复制主题到新位置，为新文档创建元数据"""
        return await self.index_manager.copy_topic_with_metadata(user_id, source_path, target_path)

    async def merge_topics(self, user_id: str, source_path: str, target_path: str, overwrite: bool = False) -> bool:
        """合并主题，同步更新文档元数据"""
        return await self.index_manager.merge_topics_with_metadata(user_id, source_path, target_path, overwrite)

    async def verify_and_repair_document_paths(self, user_id: str, topic_path: str = "") -> None:
        """验证主题下所有文档的元数据与文件系统位置一致性，并自动修复"""
        await self.index_manager.verify_and_repair_document_paths(user_id, topic_path)
