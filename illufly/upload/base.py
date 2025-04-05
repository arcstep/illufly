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
from fastapi import UploadFile

logger = logging.getLogger(__name__)

class FileStatus:
    """文件状态枚举"""
    TEMPORARY = "temporary"  # 临时文件，将自动过期
    PRESERVED = "preserved"  # 保留文件，不会自动过期
    EXPIRED = "expired"      # 已过期文件，待清理

class UploadService:
    """文件存储服务基类
    
    按用户分目录存储文件，提供上传、下载、删除和列表查询功能。
    支持文件生命周期管理，包括临时文件自动过期和清理。
    """
    
    def __init__(
        self, 
        base_dir: str, 
        max_file_size: int = 10 * 1024 * 1024, 
        max_files_per_user: int = 100,
        temp_file_expiration_days: int = 7
    ):
        """初始化文件存储服务
        
        Args:
            base_dir: 文件存储根目录
            max_file_size: 单个文件最大大小（字节），默认10MB
            max_files_per_user: 每个用户允许的最大文件数量，默认100
            temp_file_expiration_days: 临时文件过期天数，默认7天
        """
        self.base_dir = Path(base_dir)
        self.temp_dir = self.base_dir / "temp"
        self.web_cache_dir = self.base_dir / "webcache"
        
        # 创建目录
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.web_cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_file_size = max_file_size
        self.max_files_per_user = max_files_per_user
        self.temp_file_expiration_days = temp_file_expiration_days
        self._supported_file_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
        }
        
        # 启动清理任务
        self._cleanup_task = None
    
    async def start_cleanup_task(self):
        """启动定期清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_files_task())
    
    async def _cleanup_expired_files_task(self):
        """定期清理过期文件任务"""
        while True:
            try:
                await self.cleanup_expired_files()
                # 每天运行一次
                await asyncio.sleep(24 * 60 * 60)
            except Exception as e:
                logger.error(f"清理过期文件任务异常: {e}")
                await asyncio.sleep(60 * 60)  # 出错后1小时后重试
    
    async def cleanup_expired_files(self):
        """清理过期文件"""
        # 遍历所有用户目录
        logger.info("开始清理过期文件...")
        expiration_time = time.time() - (self.temp_file_expiration_days * 24 * 60 * 60)
        
        # 清理用户目录中的过期文件
        for user_dir in self.base_dir.glob("*"):
            if not user_dir.is_dir() or user_dir == self.temp_dir or user_dir == self.web_cache_dir:
                continue
            
            user_id = user_dir.name
            files = await self.list_files(user_id)
            
            for file_info in files:
                if (file_info.get("status") == FileStatus.TEMPORARY and 
                    file_info.get("created_at", 0) < expiration_time):
                    try:
                        file_id = file_info["id"]
                        await self.delete_file(user_id, file_id)
                        logger.info(f"已删除过期文件: {user_id}/{file_id}")
                    except Exception as e:
                        logger.error(f"删除过期文件失败: {user_id}/{file_id}, 错误: {e}")
        
        # 清理临时目录
        for file_path in self.temp_dir.glob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < expiration_time:
                try:
                    os.remove(file_path)
                    logger.info(f"已删除临时文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除临时文件失败: {file_path}, 错误: {e}")
        
        # 清理网页缓存目录
        for file_path in self.web_cache_dir.glob("*"):
            if file_path.is_file() and file_path.stat().st_mtime < expiration_time:
                try:
                    os.remove(file_path)
                    logger.info(f"已删除网页缓存文件: {file_path}")
                except Exception as e:
                    logger.error(f"删除网页缓存文件失败: {file_path}, 错误: {e}")
        
        logger.info("过期文件清理完成")
    
    def get_user_dir(self, user_id: str) -> Path:
        """获取用户文件目录
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户文件目录路径
        """
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def get_file_path(self, user_id: str, file_id: str) -> Path:
        """获取文件路径
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件路径
        """
        return self.get_user_dir(user_id) / file_id
    
    def get_metadata_path(self, user_id: str, file_id: str) -> Path:
        """获取文件元数据路径
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件元数据路径
        """
        return self.get_user_dir(user_id) / f"{file_id}.meta"
    
    def generate_file_id(self, original_filename: str) -> str:
        """生成文件ID
        
        Args:
            original_filename: 原始文件名
            
        Returns:
            文件ID，格式为：uuid + 文件扩展名
        """
        _, ext = os.path.splitext(original_filename)
        return f"{uuid.uuid4()}{ext}"
    
    def is_valid_file_type(self, file_name: str) -> bool:
        """检查文件类型是否有效
        
        Args:
            file_name: 文件名
            
        Returns:
            文件类型是否有效
        """
        _, ext = os.path.splitext(file_name)
        return ext.lower() in self._supported_file_types
    
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
        return self._supported_file_types.get(ext.lower(), 'application/octet-stream')
    
    async def save_file(
        self, 
        user_id: str, 
        file: UploadFile, 
        status: str = FileStatus.TEMPORARY
    ) -> Dict[str, Any]:
        """保存文件
        
        Args:
            user_id: 用户ID
            file: 上传的文件
            status: 文件状态，默认为临时文件
            
        Returns:
            文件信息，包含ID、原始文件名、大小等
            
        Raises:
            ValueError: 文件大小超过限制、文件类型不支持或用户文件数量超过限制
        """
        # 检查文件类型
        if not self.is_valid_file_type(file.filename):
            raise ValueError(f"不支持的文件类型: {file.filename}")
        
        # 检查用户文件数量
        user_dir = self.get_user_dir(user_id)
        existing_files = list(user_dir.glob("*"))
        if len(existing_files) >= self.max_files_per_user * 2:  # 因为每个文件有元数据文件
            raise ValueError(f"用户文件数量超过限制: {self.max_files_per_user}")
        
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
        
        # 生成文件信息
        file_info = {
            "id": file_id,
            "original_name": file.filename,
            "size": file_size,
            "type": self.get_file_type(file.filename),
            "path": str(file_path),
            "created_at": time.time(),
            "status": status,
            "source_type": "upload",
            "source": file.filename
        }
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info))
        
        return file_info
    
    async def save_web_file(
        self, 
        user_id: str, 
        url: str, 
        file_content: bytes, 
        file_type: str,
        status: str = FileStatus.TEMPORARY
    ) -> Dict[str, Any]:
        """保存从网页抓取的文件
        
        Args:
            user_id: 用户ID
            url: 网页地址
            file_content: 文件内容
            file_type: 文件类型
            status: 文件状态，默认为临时文件
            
        Returns:
            文件信息
            
        Raises:
            ValueError: 文件大小超过限制或用户文件数量超过限制
        """
        # 检查用户文件数量
        user_dir = self.get_user_dir(user_id)
        existing_files = list(user_dir.glob("*"))
        if len(existing_files) >= self.max_files_per_user * 2:  # 因为每个文件有元数据文件
            raise ValueError(f"用户文件数量超过限制: {self.max_files_per_user}")
        
        # 检查文件大小
        file_size = len(file_content)
        if file_size > self.max_file_size:
            raise ValueError(f"文件大小超过限制: {self.max_file_size} bytes")
        
        # 从URL生成文件名
        url_filename = url.split('/')[-1]
        if '.' not in url_filename:
            url_filename = f"web_content.{file_type}"
        
        # 生成文件ID和路径
        file_id = self.generate_file_id(url_filename)
        file_path = self.get_file_path(user_id, file_id)
        meta_path = self.get_metadata_path(user_id, file_id)
        
        # 保存文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(file_content)
        
        # 生成文件信息
        file_info = {
            "id": file_id,
            "original_name": url_filename,
            "size": file_size,
            "type": file_type,
            "path": str(file_path),
            "created_at": time.time(),
            "status": status,
            "source_type": "web",
            "source": url
        }
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info))
        
        return file_info
    
    async def cache_web_file(self, url: str, file_content: bytes, file_type: str) -> str:
        """缓存网页文件到临时目录
        
        Args:
            url: 网页地址
            file_content: 文件内容
            file_type: 文件类型
            
        Returns:
            缓存文件路径
        """
        # 生成文件名 (URL的MD5 + 文件类型)
        import hashlib
        url_hash = hashlib.md5(url.encode()).hexdigest()
        file_name = f"{url_hash}.{file_type}"
        file_path = self.web_cache_dir / file_name
        
        # 保存文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(file_content)
        
        return str(file_path)
    
    async def get_file(self, user_id: str, file_id: str) -> Optional[Dict[str, Any]]:
        """获取文件信息
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件信息，如果文件不存在则返回None
        """
        file_path = self.get_file_path(user_id, file_id)
        meta_path = self.get_metadata_path(user_id, file_id)
        
        if not file_path.exists() or not meta_path.exists():
            return None
        
        # 读取元数据
        async with aiofiles.open(meta_path, 'r') as meta_file:
            meta_content = await meta_file.read()
            return json.loads(meta_content)
    
    async def update_file_status(self, user_id: str, file_id: str, status: str) -> bool:
        """更新文件状态
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            status: 新状态
            
        Returns:
            是否更新成功
        """
        file_info = await self.get_file(user_id, file_id)
        if not file_info:
            return False
        
        # 更新状态
        file_info["status"] = status
        meta_path = self.get_metadata_path(user_id, file_id)
        
        # 保存元数据
        async with aiofiles.open(meta_path, 'w') as meta_file:
            await meta_file.write(json.dumps(file_info))
        
        return True
    
    async def preserve_file(self, user_id: str, file_id: str) -> bool:
        """标记文件为保留状态（不会自动过期）
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            是否操作成功
        """
        return await self.update_file_status(user_id, file_id, FileStatus.PRESERVED)
    
    async def delete_file(self, user_id: str, file_id: str) -> bool:
        """删除文件
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            是否删除成功
        """
        file_path = self.get_file_path(user_id, file_id)
        meta_path = self.get_metadata_path(user_id, file_id)
        
        success = True
        
        # 删除文件
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception as e:
                logger.error(f"删除文件失败: {file_path}, 错误: {e}")
                success = False
        
        # 删除元数据
        if meta_path.exists():
            try:
                os.remove(meta_path)
            except Exception as e:
                logger.error(f"删除文件元数据失败: {meta_path}, 错误: {e}")
                success = False
        
        return success
    
    async def list_files(self, user_id: str) -> List[Dict[str, Any]]:
        """列出用户所有文件
        
        Args:
            user_id: 用户ID
            
        Returns:
            文件信息列表
        """
        user_dir = self.get_user_dir(user_id)
        files = []
        
        # 查找所有元数据文件
        for meta_path in user_dir.glob("*.meta"):
            try:
                async with aiofiles.open(meta_path, 'r') as meta_file:
                    meta_content = await meta_file.read()
                    file_info = json.loads(meta_content)
                    
                    # 检查文件是否存在
                    file_path = Path(file_info["path"])
                    if not file_path.exists():
                        continue
                    
                    files.append(file_info)
            except Exception as e:
                logger.error(f"读取文件元数据失败: {meta_path}, 错误: {e}")
        
        return files
    
    def get_download_url(self, user_id: str, file_id: str) -> str:
        """获取文件下载URL
        
        Args:
            user_id: 用户ID
            file_id: 文件ID
            
        Returns:
            文件下载URL
        """
        return f"/api/docs/{file_id}/download"
