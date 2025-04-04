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

logger = logging.getLogger(__name__)

try:
    from docling.datamodel.document import InputDocument, InputFormat, DocumentLimits
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.backend.abstract_backend import AbstractDocumentBackend
    DOCLING_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import docling: {e}")
    DOCLING_AVAILABLE = False

from .models import DocumentProcessStage, DocumentProcessStatus

class DocumentLoader:
    """文档加载器"""
    
    def __init__(self, status_tracker: DocumentProcessStatus):
        """初始化文档加载器
        
        Args:
            status_tracker: 状态追踪器
        """
        self.status_tracker = status_tracker
        self._intermediate_results = {}
        
        # 支持的格式映射
        self._supported_formats = {
            # 文档格式
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'doc': 'application/msword',
            'xls': 'application/vnd.ms-excel',
            'ppt': 'application/vnd.ms-powerpoint',
            
            # 标记语言
            'markdown': 'text/markdown',
            'asciidoc': 'text/asciidoc',
            'html': 'text/html',
            'xhtml': 'application/xhtml+xml',
            
            # 数据格式
            'csv': 'text/csv',
            'json': 'application/json',
            
            # 图片格式
            'png': 'image/png',
            'jpeg': 'image/jpeg',
            'tiff': 'image/tiff',
            'bmp': 'image/bmp',
            
            # XML格式
            'xml': 'application/xml',
            'uspto': 'application/xml',
            'jats': 'application/xml',
            
            # 其他
            'txt': 'text/plain'
        }
        
        # 扩展名映射
        self._extension_map = {
            '.md': 'markdown',
            '.adoc': 'asciidoc',
            '.htm': 'html',
            '.jpg': 'jpeg',
            '.jpeg': 'jpeg',
            '.uspto': 'xml',
            '.jats': 'xml'
        }
        
        # 格式到InputFormat的映射
        self._format_to_input_format = {
            'pdf': InputFormat.PDF,
            'docx': InputFormat.DOCX,
            'xlsx': InputFormat.XLSX,
            'pptx': InputFormat.PPTX,
            'html': InputFormat.HTML,
            'asciidoc': InputFormat.ASCIIDOC,
            'md': InputFormat.MD,
            'csv': InputFormat.CSV,
            'xml_uspto': InputFormat.XML_USPTO,
            'xml_jats': InputFormat.XML_JATS
        }
    
    def _detect_file_format(self, source: str) -> Tuple[str, str]:
        """检测文档格式
        
        Args:
            source: 文档源（文件路径或URL）
            
        Returns:
            (格式类型, MIME类型)
        """
        # 检查是否是URL
        try:
            result = urllib.parse.urlparse(source)
            is_url = all([result.scheme, result.netloc])
        except:
            is_url = False
            
        if is_url:
            # 特殊处理arxiv PDF URL
            if 'arxiv.org/pdf' in source:
                return 'pdf', 'application/pdf'
                
            # 尝试从URL路径中获取扩展名
            ext = os.path.splitext(result.path)[1].lower()
            if ext:
                # 检查扩展名映射
                if ext in self._extension_map:
                    format_type = self._extension_map[ext]
                    return format_type, self._supported_formats[format_type]
                    
                # 去掉点号
                ext = ext[1:]
                if ext in self._supported_formats:
                    return ext, self._supported_formats[ext]
                    
            # 尝试通过HEAD请求获取Content-Type
            try:
                response = requests.head(source)
                content_type = response.headers.get('Content-Type', '').lower()
                
                # 检查Content-Type映射
                for format_type, mime_type in self._supported_formats.items():
                    if content_type.startswith(mime_type):
                        return format_type, mime_type
            except:
                pass
                
            # 默认返回HTML
            return 'html', 'text/html'
        else:
            # 本地文件
            ext = os.path.splitext(source)[1].lower()
            if not ext:
                return 'unknown', 'application/octet-stream'
                
            # 检查扩展名映射
            if ext in self._extension_map:
                format_type = self._extension_map[ext]
                return format_type, self._supported_formats[format_type]
                
            # 去掉点号
            ext = ext[1:]
            if ext in self._supported_formats:
                return ext, self._supported_formats[ext]
                
            # 尝试使用mimetypes
            mime_type, _ = mimetypes.guess_type(source)
            if mime_type:
                for format_type, supported_mime in self._supported_formats.items():
                    if mime_type.startswith(supported_mime):
                        return format_type, supported_mime
                        
            return 'unknown', 'application/octet-stream'
    
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
        
        # 获取InputFormat
        input_format = self._format_to_input_format.get(format_type, InputFormat.PDF)
        
        # 创建输入文档
        kwargs = {
            'path_or_stream': Path(source),
            'format': input_format,
            'backend': PyPdfiumDocumentBackend if format_type == 'pdf' else AbstractDocumentBackend,
            'filename': os.path.basename(source),
            'limits': DocumentLimits()
        }
        
        # 添加元数据
        if metadata:
            kwargs['metadata'] = metadata
            
        in_doc = InputDocument(**kwargs)
        
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