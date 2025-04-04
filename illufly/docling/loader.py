"""文档加载器模块

提供文档加载和识别功能，包括：
1. 文档加载器
2. 文档格式识别
3. 文档预处理
"""

import logging
import os
import mimetypes
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import urllib.parse
import requests

try:
    from docling.datamodel.document import InputDocument
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

from .base import DocumentProcessStage, DocumentProcessStatus

logger = logging.getLogger(__name__)

class DocumentLoader:
    """文档加载器"""
    
    def __init__(self, status_tracker: DocumentProcessStatus):
        """初始化文档加载器
        
        Args:
            status_tracker: 处理状态追踪器
        """
        self.status_tracker = status_tracker
        self._supported_formats = {
            # 文档格式
            'pdf': ['application/pdf'],
            'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
            'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
            'pptx': ['application/vnd.openxmlformats-officedocument.presentationml.presentation'],
            'doc': ['application/msword'],
            'xls': ['application/vnd.ms-excel'],
            'ppt': ['application/vnd.ms-powerpoint'],
            
            # 标记语言
            'md': ['text/markdown', 'text/x-markdown'],
            'markdown': ['text/markdown', 'text/x-markdown'],
            'adoc': ['text/asciidoc'],
            'asciidoc': ['text/asciidoc'],
            'html': ['text/html'],
            'htm': ['text/html'],
            'xhtml': ['application/xhtml+xml'],
            
            # 数据格式
            'csv': ['text/csv', 'application/csv'],
            'json': ['application/json'],
            
            # 图片格式
            'png': ['image/png'],
            'jpg': ['image/jpeg'],
            'jpeg': ['image/jpeg'],
            'tiff': ['image/tiff'],
            'bmp': ['image/bmp'],
            
            # XML格式
            'xml': ['application/xml', 'text/xml'],
            'uspto': ['application/xml'],  # USPTO专利XML
            'jats': ['application/xml'],   # JATS文章XML
            
            # 其他
            'txt': ['text/plain'],
            'url': ['text/html']  # URL特殊处理
        }
        
        # 扩展名映射
        self._extension_map = {
            'md': 'markdown',
            'adoc': 'asciidoc',
            'htm': 'html',
            'jpg': 'jpeg',
            'uspto': 'xml',
            'jats': 'xml'
        }
    
    def _detect_file_format(self, source: str) -> Tuple[str, str]:
        """检测文件格式
        
        Args:
            source: 文件路径或URL
            
        Returns:
            (格式类型, MIME类型)
        """
        # 检查是否为URL
        parsed = urllib.parse.urlparse(source)
        if parsed.scheme in ('http', 'https'):
            # 从URL路径中提取文件扩展名
            path = parsed.path.lower()
            for ext, format_type in self._extension_map.items():
                if path.endswith(f'.{ext}'):
                    return format_type, self._supported_formats[format_type][0]
            
            # 检查直接支持的扩展名
            for ext, mimes in self._supported_formats.items():
                if path.endswith(f'.{ext}'):
                    return ext, mimes[0]
            
            # 尝试通过HEAD请求获取Content-Type
            try:
                response = requests.head(source, allow_redirects=True)
                content_type = response.headers.get('Content-Type', '').lower()
                
                # 检查Content-Type
                for fmt, mimes in self._supported_formats.items():
                    if any(mime in content_type for mime in mimes):
                        return fmt, content_type
            except Exception as e:
                logger.warning(f"无法获取URL的Content-Type: {str(e)}")
            
            # 默认返回URL类型
            return 'url', 'text/html'
        
        # 检查文件扩展名
        ext = os.path.splitext(source)[1].lower().lstrip('.')
        
        # 检查扩展名映射
        if ext in self._extension_map:
            format_type = self._extension_map[ext]
            return format_type, self._supported_formats[format_type][0]
        
        # 检查直接支持的扩展名
        if ext in self._supported_formats:
            return ext, self._supported_formats[ext][0]
        
        # 使用mimetypes猜测
        mime_type, _ = mimetypes.guess_type(source)
        if mime_type:
            for fmt, mimes in self._supported_formats.items():
                if mime_type in mimes:
                    return fmt, mime_type
        
        return 'unknown', mime_type or 'application/octet-stream'
    
    def load_document(self, source: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[InputDocument, str]:
        """加载文档
        
        Args:
            source: 文档源（文件路径或URL）
            metadata: 文档元数据
            
        Returns:
            (输入文档, 格式类型)
        """
        if not DOCLING_AVAILABLE:
            raise ImportError("docling包未安装，无法加载文档")
        
        # 检测文档格式
        format_type, mime_type = self._detect_file_format(source)
        logger.info(f"检测到文档格式: {format_type} (MIME: {mime_type})")
        
        # 更新状态
        self.status_tracker.update(
            DocumentProcessStage.INITIALIZED,
            0.1,
            f"检测到文档格式: {format_type}"
        )
        
        # 创建输入文档
        in_doc = InputDocument(
            file=Path(source),
            mime_type=mime_type,
            metadata=metadata or {}
        )
        
        return in_doc, format_type
    
    def download_document(self, url: str, save_path: Optional[str] = None) -> str:
        """下载文档
        
        Args:
            url: 文档URL
            save_path: 保存路径，如果为None则使用临时目录
            
        Returns:
            保存的文件路径
        """
        if not save_path:
            save_path = os.path.join('/tmp', os.path.basename(url))
        
        # 更新状态
        self.status_tracker.update(
            DocumentProcessStage.DOWNLOADING,
            0.2,
            f"正在下载文档: {url}"
        )
        
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    downloaded += len(data)
                    f.write(data)
                    
                    # 更新下载进度
                    if total_size > 0:
                        progress = downloaded / total_size
                        self.status_tracker.update(
                            DocumentProcessStage.DOWNLOADING,
                            0.2 + progress * 0.3,
                            f"下载进度: {progress:.1%}"
                        )
            
            logger.info(f"文档下载完成: {save_path}")
            return save_path
            
        except Exception as e:
            error_msg = f"文档下载失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.status_tracker.fail(error_msg)
            raise 