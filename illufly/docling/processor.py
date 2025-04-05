"""文档处理器模块

提供高级接口，统一处理各种格式的文档并产生异步结果流。
方便应用层和对话系统集成。
"""

import logging
import time
import asyncio
import sys
from typing import Dict, Any, Optional, Callable, AsyncGenerator, Union, List, Type, Tuple, Iterator
from pathlib import Path
from datetime import datetime
import traceback
from functools import partial
from copy import deepcopy

# 从官方docling导入
from docling.document_converter import FormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.document import InputDocument, ConversionResult
from docling.chunking import BaseChunker, BaseChunk, HybridChunker
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.simple_pipeline import SimplePipeline

# 从当前模块导入
from .schemas import DocumentProcessStage, DocumentProcessStatus
from .converter import ObservableConverter
from .chunker import ObservableChunker

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """统一文档处理器
    
    提供高级接口，统一处理各种格式的文档并产生异步结果流。
    方便应用层和对话系统集成。
    """
    
    def __init__(
        self,
        allowed_formats: Optional[List[InputFormat]] = None,
        format_options: Optional[Dict[InputFormat, FormatOption]] = None,
        enable_remote_services: bool = False,
        do_picture_description: bool = False,
        enable_code_enrichment: bool = True,
        enable_formula_enrichment: bool = True,
        artifacts_path: Optional[str] = None,
        use_stable_backend: bool = True
    ):
        """初始化文档处理器
        
        Args:
            allowed_formats: 允许处理的文档格式
            format_options: 格式处理选项
            enable_remote_services: 是否启用远程服务
            do_picture_description: 是否描述图片
            enable_code_enrichment: 是否识别代码
            enable_formula_enrichment: 是否识别公式
            artifacts_path: 模型路径
            use_stable_backend: 是否使用稳定的后端组合（推荐启用）
        """
        # 保存配置选项以便后续访问
        self._enable_remote_services = enable_remote_services
        self._do_picture_description = do_picture_description
        self._enable_code_enrichment = enable_code_enrichment
        self._enable_formula_enrichment = enable_formula_enrichment
        self._artifacts_path = artifacts_path
        
        # 如果未提供格式选项，创建默认选项
        if not format_options and use_stable_backend:
            format_options = self._get_default_format_options()
        elif format_options and use_stable_backend:
            # 合并用户选项与默认选项
            default_options = self._get_default_format_options()
            for fmt, opt in default_options.items():
                if fmt not in format_options:
                    format_options[fmt] = opt
        
        self.format_options = format_options or {}
        
        # 如果有PDF选项，增强其功能配置
        if InputFormat.PDF in self.format_options:
            pdf_option = self.format_options[InputFormat.PDF]
            if hasattr(pdf_option, 'pipeline_options') and pdf_option.pipeline_options is not None:
                pdf_option.pipeline_options.do_picture_description = do_picture_description
                pdf_option.pipeline_options.enable_remote_services = enable_remote_services
                pdf_option.pipeline_options.do_code_enrichment = enable_code_enrichment
                pdf_option.pipeline_options.do_formula_enrichment = enable_formula_enrichment
                
                if artifacts_path:
                    pdf_option.pipeline_options.artifacts_path = artifacts_path
        
        # 创建可观测转换器
        self.converter = ObservableConverter(
            allowed_formats=allowed_formats,
            format_options=self.format_options
        )
    
    def _get_default_format_options(self) -> Dict[InputFormat, FormatOption]:
        """获取默认格式选项
        
        为不同格式配置安全稳定的默认选项
        
        Returns:
            格式选项字典
        """
        default_options = {}
        
        # 配置PDF格式选项
        pdf_pipeline_options = PdfPipelineOptions()
        pdf_pipeline_options.enable_remote_services = self._enable_remote_services
        pdf_pipeline_options.do_ocr = False
        pdf_pipeline_options.do_table_structure = False
        pdf_pipeline_options.do_formula_enrichment = self._enable_formula_enrichment
        pdf_pipeline_options.do_picture_description = self._do_picture_description
        pdf_pipeline_options.do_code_enrichment = self._enable_code_enrichment
        
        if self._artifacts_path:
            pdf_pipeline_options.artifacts_path = self._artifacts_path
        
        # 显式指定PyPdfiumDocumentBackend和SimplePipeline组合，避免使用DoclingParseV4DocumentBackend
        default_options[InputFormat.PDF] = PdfFormatOption(
            backend=PyPdfiumDocumentBackend,
            pipeline_type=SimplePipeline,
            pipeline_options=pdf_pipeline_options
        )
        
        return default_options
    
    async def process_document(
        self,
        file_path: Union[str, Path],
        raise_on_error: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理文档并产生异步结果流
        
        Args:
            file_path: 文档路径或URL
            raise_on_error: 错误时是否抛出异常
            
        Yields:
            状态更新和处理结果
        """
        # 创建状态跟踪器
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        status_tracker = DocumentProcessStatus(doc_id=doc_id)
        
        # 使用异步转换器处理文档
        async for update in self.converter.convert_async(
            source=file_path,
            status_tracker=status_tracker,
            raises_on_error=raise_on_error
        ):
            yield update
            
            # 如果是处理结果，提取文档元素并单独yield
            if isinstance(update, dict) and update.get("type") == "result":
                result = update.get("result")
                if result and hasattr(result, "document") and result.document:
                    # 提取文本
                    try:
                        text = result.document.export_to_text()
                        if text:
                            yield {
                                "type": "text",
                                "content": text,
                                "doc_id": doc_id
                            }
                    except Exception as e:
                        logger.warning(f"提取文本失败: {str(e)}")
                    
                    # 提取元素 - 将异步生成器转换为列表后再yield
                    try:
                        elements = []
                        async for element in self._extract_and_yield_elements(result.document, doc_id):
                            elements.append(element)
                        
                        # 然后再yield每个元素
                        for element in elements:
                            yield element
                    except Exception as e:
                        logger.warning(f"提取元素失败: {str(e)}")
    
    async def _extract_and_yield_elements(self, document, doc_id: str):
        """提取并yield文档中的各种元素
        
        Args:
            document: docling文档对象
            doc_id: 文档ID
        
        Yields:
            文档元素
        """
        # 提取表格
        if hasattr(document, 'tables') and document.tables:
            for i, table in enumerate(document.tables):
                table_data = self._extract_table(table)
                yield {
                    "type": "table",
                    "content": table_data,
                    "index": i,
                    "doc_id": doc_id
                }
        
        # 提取图片
        if hasattr(document, 'pictures') and document.pictures:
            for i, pic in enumerate(document.pictures):
                image_data = self._extract_image(pic)
                if image_data:
                    yield {
                        "type": "image",
                        "content": image_data.get("data"),
                        "description": image_data.get("description", ""),
                        "index": i,
                        "doc_id": doc_id
                    }
    
    def _extract_table(self, table) -> Dict[str, Any]:
        """从docling表格对象提取数据
        
        Args:
            table: docling表格对象
            
        Returns:
            表格数据
        """
        table_data = {
            "rows": [],
            "caption": table.caption if hasattr(table, "caption") else ""
        }
        
        # 提取行和单元格
        if hasattr(table, 'rows'):
            for row in table.rows:
                row_data = []
                if hasattr(row, 'cells'):
                    for cell in row.cells:
                        cell_text = cell.text if hasattr(cell, "text") else ""
                        row_data.append(cell_text)
                table_data["rows"].append(row_data)
        
        return table_data
    
    def _extract_image(self, pic) -> Dict[str, Any]:
        """从docling图片对象提取数据
        
        Args:
            pic: docling图片对象
            
        Returns:
            图片数据
        """
        image_data = {
            "data": pic.data if hasattr(pic, "data") else None,
            "width": pic.width if hasattr(pic, "width") else 0,
            "height": pic.height if hasattr(pic, "height") else 0
        }
        
        # 如果有图片描述
        if hasattr(pic, 'description') and pic.description:
            image_data["description"] = pic.description
        
        return image_data

    async def process_and_chunk_document(
        self,
        file_path: Union[str, Path],
        chunker: Optional[BaseChunker] = None,
        tokenizer: Optional[str] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        raise_on_error: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理文档并进行分块，产生异步结果流
        
        Args:
            file_path: 文档路径或URL
            chunker: 自定义分块器，如果为None则使用HybridChunker
            tokenizer: 分词器名称（用于创建HybridChunker，当chunker为None时使用）
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠大小（字符数）
            raise_on_error: 错误时是否抛出异常
            
        Yields:
            状态更新、处理结果和分块结果
        """
        # 创建状态跟踪器
        doc_id = f"doc_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        status_tracker = DocumentProcessStatus(doc_id=doc_id)
        
        # 声明结果文档变量
        result_document = None
        
        # 处理文档
        async for update in self.converter.convert_async(
            source=file_path,
            status_tracker=status_tracker,
            raises_on_error=raise_on_error
        ):
            yield update
            
            # 如果是处理结果，提取文档元素并单独yield
            if isinstance(update, dict) and update.get("type") == "result":
                result = update.get("result")
                if result and hasattr(result, "document") and result.document:
                    # 保存文档对象供后续分块使用
                    result_document = result.document
                    
                    # 提取文本
                    try:
                        text = result.document.export_to_text()
                        if text:
                            yield {
                                "type": "text",
                                "content": text,
                                "doc_id": doc_id
                            }
                    except Exception as e:
                        logger.warning(f"提取文本失败: {str(e)}")
                    
                    # 提取元素
                    try:
                        elements = []
                        async for element in self._extract_and_yield_elements(result.document, doc_id):
                            elements.append(element)
                        
                        # 然后再yield每个元素
                        for element in elements:
                            yield element
                    except Exception as e:
                        logger.warning(f"提取元素失败: {str(e)}")
        
        # 如果没有获取到文档对象或发生了错误，就不进行分块
        if not result_document:
            logger.warning("文档处理未返回有效的文档对象，无法进行分块")
            return
        
        # 如果没有提供分块器，使用默认的HybridChunker
        if chunker is None:
            try:
                chunker = HybridChunker(
                    tokenizer=tokenizer or "BAAI/bge-small-en-v1.5",
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap
                )
            except Exception as e:
                logger.error(f"创建默认分块器失败: {str(e)}")
                if raise_on_error:
                    raise
                return
        
        # 创建可观测分块器
        chunk_status_tracker = DocumentProcessStatus(doc_id=f"chunk_{doc_id}")
        observable_chunker = ObservableChunker(chunker, chunk_status_tracker)
        
        # 执行异步分块
        async for chunk_update in observable_chunker.chunk_async(result_document):
            yield chunk_update


async def create_async_observable_converter(
    status_tracker: DocumentProcessStatus, 
    do_picture_description: bool = False,
    raise_on_error: bool = True,
    enable_remote_services: bool = False,
    enable_code_enrichment: bool = True,
    enable_formula_enrichment: bool = True,
    artifacts_path: Optional[str] = None,
    use_stable_backend: bool = True
) -> AsyncGenerator[Dict[str, Any], None]:
    """创建异步可观测转换器并产生状态流
    
    这是一个便捷工厂函数，创建一个临时的DocumentProcessor处理器，
    初始化所需配置并返回转换器对象，以兼容之前的接口。
    
    Args:
        status_tracker: 状态追踪器
        do_picture_description: 是否描述图片
        raise_on_error: 错误时是否抛出异常
        enable_remote_services: 是否启用远程服务
        enable_code_enrichment: 是否识别代码
        enable_formula_enrichment: 是否识别公式
        artifacts_path: 模型路径
        use_stable_backend: 是否使用稳定后端配置（推荐启用）
        
    Yields:
        状态更新和转换器
    """
    # 初始化状态
    logger.info(f"正在初始化文档转换器 [doc_id={status_tracker.doc_id}]")
    status_tracker.update(
        stage=DocumentProcessStage.INIT,
        progress=0.1,
        message="初始化文档转换器"
    )
    
    # 产生初始状态
    yield status_tracker.to_dict()
    
    try:
        # 创建处理器
        processor = DocumentProcessor(
            do_picture_description=do_picture_description,
            enable_remote_services=enable_remote_services,
            enable_code_enrichment=enable_code_enrichment,
            enable_formula_enrichment=enable_formula_enrichment,
            artifacts_path=artifacts_path,
            use_stable_backend=use_stable_backend
        )
        
        # 更新状态
        status_tracker.update(
            stage=DocumentProcessStage.PROCESSING,
            progress=0.5,
            message="转换器准备就绪"
        )
        yield status_tracker.to_dict()
        
        # 创建异步处理方法
        async def process_document_async(in_doc: InputDocument, raises_on_error: bool = True) -> AsyncGenerator[Dict[str, Any], None]:
            """异步处理文档，产生状态更新
            
            Args:
                in_doc: 输入文档
                raises_on_error: 错误时是否抛出异常
                
            Yields:
                状态更新和处理结果
            """
            # 使用processor的converter处理文档
            observable_pipeline = processor.converter._wrap_pipeline(
                processor.converter.converter._get_pipeline(in_doc.format),
                status_tracker
            )
            
            # 执行异步处理
            async for item in observable_pipeline.execute_async(in_doc, raises_on_error):
                yield item
        
        # 创建结果对象
        result = {
            "type": "converter",
            "converter": {
                "process_document_async": process_document_async,
                "status": "ready"
            }
        }
        
        # 返回转换器
        yield result
        
    except Exception as e:
        error_msg = f"创建转换器过程中出现异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        status_tracker.update(
            stage=DocumentProcessStage.ERROR,
            progress=0.0,
            error=str(e)
        )
        yield status_tracker.to_dict()
        
        if raise_on_error:
            raise 