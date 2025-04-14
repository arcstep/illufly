from typing import List, Dict, Any, Optional
from pathlib import Path
import os
import shutil
import uuid
import time
import aiofiles
import logging
import mimetypes
import asyncio
import json
from fastapi import UploadFile, HTTPException, Depends, APIRouter, File, Form

logger = logging.getLogger(__name__)

class FileStatus:
    """文件状态枚举"""
    ACTIVE = "active"      # 活跃文件
    DELETED = "deleted"    # 已删除文件
    PROCESSING = "processing"  # 处理中的文件

class FilesService:
    """文件管理服务
    
    按用户分目录存储文件，提供上传、下载、删除和列表查询功能。
    支持元数据管理、文件处理和流式下载。
    """
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 50 * 1024 * 1024,  # 默认50MB 
        max_total_size_per_user: int = 200 * 1024 * 1024,  # 默认200MB
        allowed_extensions: List[str] = None
    ):
        """初始化文件管理服务
        
        Args:
            base_dir: 文件存储根目录
            max_file_size: 单个文件最大大小（字节），默认50MB
            max_total_size_per_user: 每个用户允许的最大存储总大小，默认200MB
            allowed_extensions: 允许的文件扩展名列表，默认为None表示允许所有扩展名
        """
        self.base_dir = Path(base_dir)
        self.files_dir = self.base_dir / "files"
        self.meta_dir = self.base_dir / "meta"
        self.temp_dir = self.base_dir / "temp"
        
        # 创建目录
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.max_total_size_per_user = max_total_size_per_user
        self.allowed_extensions = allowed_extensions or [
            '.ppt', '.pptx',
            '.rmd', '.md', '.mdx', '.markdown',
            '.pdf', '.doc', '.docx', '.txt',
            '.jpg', '.jpeg', '.png', '.gif', '.webp',
            '.csv', '.xlsx', '.xls',
            '.zip', '.rar', '.7z',
            '.mp3', '.wav', '.mp4', '.avi', '.mov'
        ]
        
        # 文件MIME类型映射
        self._mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.markdown': 'text/markdown',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.csv': 'text/csv',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.xls': 'application/vnd.ms-excel',
            '.zip': 'application/zip',
            '.rar': 'application/x-rar-compressed',
            '.7z': 'application/x-7z-compressed',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
        }
    
    def get_user_files_dir(self, user_id: str) -> Path:
        """获取用户文件目录
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户文件目录路径
        """
        user_dir = self.files_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_user_meta_dir(self, user_id: str) -> Path:
        """获取用户元数据目录
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户元数据目录路径
        """
        user_meta_dir = self.meta_dir / user_id
        user_meta_dir.mkdir(parents=True, exist_ok=True)
        return user_meta_dir
    
    def get_user_temp_dir(self, user_id: str) -> Path:
        """获取用户临时文件目录
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户临时文件目录路径
        """
        user_temp_dir = self.temp_dir / user_id
        user_temp_dir.mkdir(parents=True, exist_ok=True)
        return user_temp_dir
    
    def get_file_path(self, user_id: str, file_id: str) -> Path:
        """获取文件路径
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件路径
        """
        return self.get_user_files_dir(user_id) / file_id
    
    def get_metadata_path(self, user_id: str, file_id: str) -> Path:
        """获取文件元数据路径
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件元数据路径
        """
        return self.get_user_meta_dir(user_id) / f"{file_id}.json"
    
    def generate_file_id(self, original_filename: str) -> str:
        """生成文件ID
        
        Args:
            original_filename: 原始文件名
            
        Returns:
            文件ID，格式为：uuid + 文件扩展名
        """
        _, ext = os.path.splitext(original_filename)
        return f"{uuid.uuid4().hex}{ext.lower()}"
    
    def is_valid_file_type(self, file_name: str) -> bool:
        """检查文件类型是否有效
        
        Args:
            file_name: 文件名
            
        Returns:
            文件类型是否有效
        """
        _, ext = os.path.splitext(file_name)
        return ext.lower() in self.allowed_extensions
    
    def get_file_extension(self, file_name: str) -> str:
        """获取文件扩展名
        
        Args:
            file_name: 文件名
            
        Returns:
            文件扩展名，如 '.pdf', '.doc'
        """
        _, ext = os.path.splitext(file_name)
        return ext.lower()
    
    def get_file_type(self, file_name: str) -> str:
        """获取文件类型
        
        Args:
            file_name: 文件名
            
        Returns:
            文件类型，如 'pdf', 'doc', 'docx', 'txt'
        """
        _, ext = os.path.splitext(file_name)
        return ext.lower()[1:]  # 去掉点号
    
    def get_file_mimetype(self, file_name: str) -> str:
        """获取文件MIME类型
        
        Args:
            file_name: 文件名
            
        Returns:
            文件MIME类型
        """
        _, ext = os.path.splitext(file_name)
        mime_type = self._mime_types.get(ext.lower())
        if not mime_type:
            # 使用系统mimetypes库猜测
            mime_type = mimetypes.guess_type(file_name)[0]
        return mime_type or 'application/octet-stream'
    
    async def calculate_user_storage_usage(self, user_id: str) -> int:
        """计算用户已使用的存储空间
        
        Args:
            user_id: 用户ID
            
        Returns:
            已使用的字节数
        """
        total_size = 0
        files = await self.list_files(user_id)
        
        for file_info in files:
            if file_info.get("status") == FileStatus.ACTIVE:
                total_size += file_info.get("size", 0)
        
        return total_size
    
    async def save_file(
        self, 
        user_id: str, 
        file: UploadFile,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """保存文件
        
        Args:
            user_id: 用户ID
            file: 上传的文件
            metadata: 额外的元数据
            
        Returns:
            文件信息，包含ID、原始文件名、大小等
            
        Raises:
            ValueError: 文件大小超过限制、文件类型不支持或用户存储空间不足
        """
        # 检查文件类型
        if not self.is_valid_file_type(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 检查用户存储空间
        current_usage = await self.calculate_user_storage_usage(user_id)
        
        # 生成文件ID和路径
        file_id = self.generate_file_id(file.filename)
        file_path = self.get_file_path(user_id, file_id)
        meta_path = self.get_metadata_path(user_id, file_id)
        
        # 保存文件
        file_size = 0
        async with aiofiles.open(file_path, 'wb') as out_file:
            # 分块读取并写入文件
            while content := await file.read(1024 * 1024):  # 每次读取1MB
                file_size += len(content)
                if file_size > self.max_file_size:
                    await out_file.close()
                    os.remove(file_path)
                    raise ValueError(f"文件大小超过限制: {self.max_file_size} bytes")
                await out_file.write(content)
        
        # 检查总存储空间
        if current_usage + file_size > self.max_total_size_per_user:
            os.remove(file_path)
            raise ValueError(f"用户存储空间不足，已使用 {current_usage} bytes，限制 {self.max_total_size_per_user} bytes")
        
        # 生成文件信息
        file_info = {
            "id": file_id,
            "original_name": file.filename,
            "size": file_size,
            "type": self.get_file_type(file.filename),
            "extension": self.get_file_extension(file.filename),
            "path": str(file_path),
            "created_at": time.time(),
            "updated_at": time.time(),
            "status": FileStatus.ACTIVE,
        }
        
        # 添加额外元数据
        if metadata:
            file_info.update(metadata)
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info, ensure_ascii=False))
        
        return file_info
    
    async def get_file(self, user_id: str, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件信息，如果文件不存在则返回None
        """
        meta_path = self.get_metadata_path(user_id, file_id)
        
        if not meta_path.exists():
            return None
        
        # 读取元数据
        async with aiofiles.open(meta_path, 'r') as meta_file:
            meta_content = await meta_file.read()
            file_info = json.loads(meta_content)
            
            # 检查文件是否存在
            file_path = Path(file_info["path"])
            if not file_path.exists() and file_info.get("status") == FileStatus.ACTIVE:
                # 文件不存在但元数据显示为活跃状态，更新状态
                file_info["status"] = FileStatus.DELETED
                async with aiofiles.open(meta_path, 'w') as update_file:
                    await update_file.write(json.dumps(file_info, ensure_ascii=False))
            
            return file_info
    
    async def update_metadata(self, user_id: str, file_id: str, metadata: Dict[str, Any]) -> bool:
        """更新文件元数据
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            metadata: 新的元数据
            
        Returns:
            是否更新成功
        """
        file_info = await self.get_file(user_id, file_id)
        if not file_info or file_info.get("status") != FileStatus.ACTIVE:
            return False
        
        # 更新元数据，但保留核心字段
        core_fields = ["id", "original_name", "size", "path", "created_at", "status"]
        for key, value in metadata.items():
            if key not in core_fields:
                file_info[key] = value
        
        # 更新更新时间
        file_info["updated_at"] = time.time()
        
        # 保存元数据
        meta_path = self.get_metadata_path(user_id, file_id)
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info, ensure_ascii=False))
        
        return True
    
    async def delete_file(self, user_id: str, file_id: str) -> bool:
        """删除文件
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            是否删除成功
        """
        file_info = await self.get_file(user_id, file_id)
        if not file_info or file_info.get("status") != FileStatus.ACTIVE:
            return False
        
        file_path = Path(file_info["path"])
        meta_path = self.get_metadata_path(user_id, file_id)
        
        success = True
        
        # 删除文件
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"删除文件失败: {file_path}, 错误: {e}")
                success = False
        
        # 更新元数据状态
        file_info["status"] = FileStatus.DELETED
        file_info["updated_at"] = time.time()
        
        # 保存元数据（保留记录）
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info, ensure_ascii=False))
        
        return success
    
    async def list_files(self, user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """列出用户所有文件
        
        Args:
            user_id: 用户ID
            include_deleted: 是否包含已删除文件
            
        Returns:
            文件信息列表
        """
        user_meta_dir = self.get_user_meta_dir(user_id)
        files = []
        
        # 查找所有元数据文件
        for meta_path in user_meta_dir.glob("*.json"):
            try:
                async with aiofiles.open(meta_path, 'r') as meta_file:
                    meta_content = await meta_file.read()
                    file_info = json.loads(meta_content)
                    
                    # 处理删除状态
                    if file_info.get("status") == FileStatus.ACTIVE:
                        # 检查文件是否存在
                        file_path = Path(file_info["path"])
                        if not file_path.exists():
                            file_info["status"] = FileStatus.DELETED
                            async with aiofiles.open(meta_path, 'w') as update_file:
                                await update_file.write(json.dumps(file_info, ensure_ascii=False))
                    
                    # 根据筛选条件添加
                    if include_deleted or file_info.get("status") == FileStatus.ACTIVE:
                        files.append(file_info)
            except Exception as e:
                logger.error(f"读取文件元数据失败: {meta_path}, 错误: {e}")
        
        # 按创建时间降序排序
        files.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return files
    
    def get_download_url(self, user_id: str, file_id: str) -> str:
        """获取文件下载URL
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件下载URL
        """
        return f"/api/files/{file_id}/download"
    
    def get_preview_url(self, user_id: str, file_id: str) -> str:
        """获取文件预览URL
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件预览URL
        """
        return f"/api/files/{file_id}/preview"
    
    async def get_file_stream(self, user_id: str, file_id: str, chunk_size: int = 1024 * 1024):
        """流式读取文件内容
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            chunk_size: 分块大小，默认1MB
            
        Yields:
            文件内容分块
        """
        file_info = await self.get_file(user_id, file_id)
        if not file_info or file_info.get("status") != FileStatus.ACTIVE:
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        file_path = Path(file_info["path"])
        if not file_path.exists():
            # 文件物理不存在但元数据存在，更新状态
            file_info["status"] = FileStatus.DELETED
            meta_path = self.get_metadata_path(user_id, file_id)
            async with aiofiles.open(meta_path, 'w') as meta_file:
                await meta_file.write(json.dumps(file_info, ensure_ascii=False))
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        # 流式读取文件
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(chunk_size):
                yield chunk
    
    async def process_file(self, user_id: str, file_id: str, process_type: str) -> Dict[str, Any]:
        """处理文件（切片、转换等）
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            process_type: 处理类型，如'slice', 'convert'等
            
        Returns:
            处理结果
        """
        file_info = await self.get_file(user_id, file_id)
        if not file_info or file_info.get("status") != FileStatus.ACTIVE:
            raise FileNotFoundError(f"文件不存在: {file_id}")
        
        # 更新状态为处理中
        file_info["status"] = FileStatus.PROCESSING
        file_info["process_type"] = process_type
        file_info["process_started_at"] = time.time()
        
        meta_path = self.get_metadata_path(user_id, file_id)
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info, ensure_ascii=False))
        
        # 这里放置处理逻辑，目前仅做占位
        # TODO: 实现具体文件处理逻辑
        
        # 模拟处理延迟
        await asyncio.sleep(1)
        
        # 更新处理完成状态
        file_info["status"] = FileStatus.ACTIVE
        file_info["processed"] = True
        file_info["process_completed_at"] = time.time()
        
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info, ensure_ascii=False))
        
        return file_info

