import logging
import os
import sys
import datetime
import time
import asyncio

from pathlib import Path
from typing import Optional, List, Dict, Any, Union, AsyncGenerator

from .converter import ObservableConverter
from .schemas import DocumentProcessStage, DocumentProcessStatus

# 导入官方docling组件
from docling.datamodel.base_models import InputFormat, ConversionStatus
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.pipeline.simple_pipeline import SimplePipeline

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("illufly.docling.processor")


async def process_document(
    source: str,
    output_format: str = "markdown",
    output_path: Optional[str] = None,
    enable_remote_services: bool = False,
    do_ocr: bool = False,
    do_table_detection: bool = False,
    do_formula_detection: bool = False,
    enable_pic_description: bool = False,
    backend_choice: str = "auto",
    use_original_converter: bool = False
) -> AsyncGenerator[Dict[str, Any], None]:
    """异步处理文档并生成进度流

    Args:
        source: 源文件路径或URL
        output_format: 输出格式 (markdown, text, html, json)
        output_path: 输出文件路径，默认为源文件名+适当扩展名
        enable_remote_services: 是否启用远程服务
        do_ocr: 是否启用OCR
        do_table_detection: 是否启用表格检测
        do_formula_detection: 是否启用公式检测
        enable_pic_description: 是否启用图片描述
        backend_choice: 后端选择 (stable, standard, auto)
        use_original_converter: 是否使用官方转换器

    Yields:
        Dict[str, Any]: 处理状态和进度更新，格式如下：
            - {"type": "info", "message": str} - 一般信息
            - {"type": "progress", "stage": str, "progress": float, "message": str} - 进度更新
            - {"type": "result", "success": bool, "content": str, "output_path": str} - 处理结果
            - {"type": "error", "message": str} - 错误信息
    """
    try:
        # 确定输入路径
        if not source.startswith(('http://', 'https://')) and not os.path.exists(source):
            yield {"type": "error", "message": f"文件不存在: {source}"}
            return

        source_path = Path(source) if not source.startswith(('http://', 'https://')) else source
        
        # 确定输出路径
        if not output_path:
            if isinstance(source_path, Path):
                filename = source_path.stem
            else:
                # URL情况下，从URL中提取文件名
                from urllib.parse import urlparse
                path = urlparse(source).path
                filename = os.path.basename(path)
                if not filename:
                    filename = "document"
                filename = os.path.splitext(filename)[0]
            
            # 根据输出格式确定扩展名
            ext = {"markdown": ".md", "text": ".txt", "html": ".html", "json": ".json"}.get(output_format, ".md")
            output_path = f"{filename}{ext}"
        
        # 输出初始信息
        yield {"type": "info", "message": f"处理文档: {source}"}
        yield {"type": "info", "message": f"输出路径: {output_path}"}
        logger.debug(f"开始处理文档: {source} -> {output_path}")
        
        # 使用类似于官方的配置方式
        pipeline_options = PdfPipelineOptions(
            enable_remote_services=enable_remote_services,
            do_ocr=do_ocr,
            do_table_structure=do_table_detection,
            do_formula_enrichment=do_formula_detection,
            do_picture_description=enable_pic_description,
            generate_page_images=True
        )

        # 为最佳性能设置特定配置
        format_options = {}
        if backend_choice == "stable":
            # 使用稳定后端配置（SimplePipeline + PyPdfiumDocumentBackend）
            format_options[InputFormat.PDF] = PdfFormatOption(
                pipeline_cls=SimplePipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            )
        elif backend_choice == "standard":
            # 使用标准后端配置（使用官方默认配置）
            format_options[InputFormat.PDF] = PdfFormatOption(
                pipeline_options=pipeline_options
            )
        else:  # "auto"
            # 完全使用docling默认行为
            format_options = {}

        # 选择使用官方DocumentConverter或自定义ObservableConverter
        if use_original_converter:
            yield {"type": "info", "message": "使用官方DocumentConverter"}
            logger.debug("使用官方DocumentConverter")
            async for update in process_with_original_converter(
                source=source,
                format_options=format_options,
                output_format=output_format,
                output_path=output_path
            ):
                yield update
        else:
            yield {"type": "info", "message": "使用自定义ObservableConverter"}
            logger.debug("使用自定义ObservableConverter")
            async for update in process_with_observable_converter(
                source=source,
                format_options=format_options,
                output_format=output_format,
                output_path=output_path
            ):
                yield update
            
    except Exception as e:
        error_msg = f"处理文档出错: {str(e)}"
        logger.error(error_msg, exc_info=True)
        yield {"type": "error", "message": error_msg}


async def process_with_original_converter(
    source: str,
    format_options: Dict[InputFormat, Any],
    output_format: str = "markdown",
    output_path: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """使用官方DocumentConverter处理文档，并生成进度流
    
    Args:
        source: 源文件路径或URL
        format_options: 格式选项
        output_format: 输出格式
        output_path: 输出路径
        
    Yields:
        Dict[str, Any]: 处理状态和进度更新
    """
    # 创建官方转换器
    kwargs = {}
    if format_options:
        kwargs["format_options"] = format_options
    converter = DocumentConverter(**kwargs)
    
    # 使用线程池执行同步转换
    loop = asyncio.get_running_loop()
    start_time = time.time()
    
    # 提供初始进度信息
    yield {"type": "progress", "stage": "INIT", "progress": 0.0, "message": "开始同步转换文档..."}
    logger.debug("开始同步转换文档...")
    
    try:
        # 执行转换（在线程池中运行避免阻塞事件循环）
        # 因为官方转换器不提供进度更新，我们只能在等待过程中每隔一段时间发送当前状态
        conversion_task = loop.run_in_executor(
            None, 
            lambda: converter.convert(source, raises_on_error=False)
        )
        
        # 在等待转换完成的同时，定期发送进度更新
        elapsed = 0
        while not conversion_task.done():
            elapsed = time.time() - start_time
            # 每1秒发送一次进度更新
            yield {
                "type": "progress", 
                "stage": "PROCESSING", 
                "progress": 0.5,  # 由于无法获取真实进度，使用模糊值
                "message": f"正在处理文档... (已用时间: {elapsed:.1f}秒)",
                "elapsed": elapsed
            }
            await asyncio.sleep(1.0)
        
        # 获取转换结果
        result = await conversion_task
        
        # 计算耗时
        elapsed = time.time() - start_time
        status_msg = f"文档处理完成! 总耗时: {elapsed:.2f}秒, 状态: {result.status}"
        yield {
            "type": "progress", 
            "stage": "COMPLETE" if result.status == ConversionStatus.SUCCESS else "ERROR",
            "progress": 1.0,
            "message": status_msg,
            "elapsed": elapsed
        }
        logger.debug(status_msg)
        
        # 生成输出
        if result.status in [ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS] and result.document:
            content = ""
            content_type = output_format
            
            if output_format == "markdown":
                content = result.document.export_to_markdown()
                info_msg = f"导出Markdown，长度: {len(content)}字符"
            elif output_format == "text":
                content = result.document.export_to_text()
                info_msg = f"导出纯文本，长度: {len(content)}字符"
            elif output_format == "html":
                # HTML直接保存到文件
                result.document.save_as_html(output_path)
                info_msg = f"已导出HTML: {output_path}"
                content = f"已保存HTML到: {output_path}"
            elif output_format == "json":
                # JSON需要导出dict然后序列化
                import json
                content = json.dumps(result.document.export_to_dict(), ensure_ascii=False, indent=2)
                info_msg = f"导出JSON，长度: {len(content)}字符"
            else:
                content = result.document.export_to_markdown()
                info_msg = f"默认导出Markdown，长度: {len(content)}字符"
            
            yield {"type": "info", "message": info_msg}
            logger.debug(info_msg)
                
            # 保存到文件
            if output_format != "html":  # HTML已经直接保存了
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
            
            success_msg = f"已保存到文件: {output_path}"
            yield {"type": "info", "message": success_msg}
            logger.debug(success_msg)
            
            # 提供处理结果
            yield {
                "type": "result", 
                "success": True, 
                "content": content,
                "output_path": output_path,
                "content_type": content_type,
                "conversion_status": str(result.status)
            }
        else:
            error_msg = f"文档处理失败: {result.status}"
            yield {"type": "error", "message": error_msg}
            logger.error(error_msg)
            
            # 如果有错误信息，输出错误信息
            if hasattr(result, 'errors') and result.errors:
                for i, error in enumerate(result.errors):
                    error_detail = f"错误 {i+1}: {error}"
                    yield {"type": "error", "message": error_detail}
                    logger.error(error_detail)
            
            # 提供处理结果（失败）
            yield {
                "type": "result", 
                "success": False,
                "content": "",
                "output_path": output_path,
                "conversion_status": str(result.status)
            }
    
    except Exception as e:
        error_msg = f"使用官方转换器处理文档时出错: {str(e)}"
        yield {"type": "error", "message": error_msg}
        logger.error(error_msg, exc_info=True)
        
        # 提供处理结果（异常失败）
        yield {
            "type": "result", 
            "success": False,
            "content": "",
            "output_path": output_path,
            "error": str(e)
        }


async def process_with_observable_converter(
    source: str,
    format_options: Dict[InputFormat, Any],
    output_format: str = "markdown",
    output_path: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """使用自定义ObservableConverter处理文档，并生成进度流
    
    Args:
        source: 源文件路径或URL
        format_options: 格式选项
        output_format: 输出格式
        output_path: 输出路径
        
    Yields:
        Dict[str, Any]: 处理状态和进度更新
    """
    # 创建可观测转换器
    converter = ObservableConverter(format_options=format_options)
    
    # 开始异步处理
    start_time = datetime.datetime.now()
    last_progress = 0
    last_stage = None
    
    # 收集最终结果
    result = None
    
    # 异步转换文档，并获取实时更新
    async for update in converter.convert_async(source, raises_on_error=False):
        # 处理状态更新
        if isinstance(update, dict):
            if "stage" in update:
                # 处理阶段更新
                stage = update.get("stage")
                progress = update.get("progress", 0)
                message = update.get("message", "")
                
                # 统一进度格式
                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                
                # 转换成我们的标准格式
                standardized_update = {
                    "type": "progress",
                    "stage": stage,
                    "progress": progress,
                    "message": message,
                    "elapsed": elapsed
                }
                
                # 输出日志（仅在阶段或进度显著变化时）
                if stage != last_stage or (progress * 100) > (last_progress + 4):
                    logger.debug(f"阶段: {stage} | 进度: {progress*100:.0f}% | 耗时: {elapsed:.1f}秒 | {message}")
                    last_stage = stage
                    last_progress = progress * 100
                
                # yield标准化的更新
                yield standardized_update
                
            # 处理最终结果
            elif "type" in update and update["type"] == "result":
                result = update.get("result")
    
    # 处理最终结果
    if not result:
        error_msg = "文档处理未返回结果"
        yield {"type": "error", "message": error_msg}
        logger.error(error_msg)
        # 提供处理结果（失败）
        yield {
            "type": "result", 
            "success": False,
            "content": "",
            "output_path": output_path
        }
        return
    
    # 计算总耗时
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    complete_msg = f"文档处理完成! 总耗时: {elapsed:.2f}秒, 状态: {result.status}"
    
    # 发送完成状态
    yield {
        "type": "progress", 
        "stage": "COMPLETE" if result.status == ConversionStatus.SUCCESS else "ERROR",
        "progress": 1.0,
        "message": complete_msg,
        "elapsed": elapsed
    }
    logger.debug(complete_msg)
    
    # 根据输出格式导出内容
    if result.document:
        content = ""
        content_type = output_format
        
        if output_format == "markdown":
            content = result.document.export_to_markdown()
            info_msg = f"导出Markdown，长度: {len(content)}字符"
        elif output_format == "text":
            content = result.document.export_to_text()
            info_msg = f"导出纯文本，长度: {len(content)}字符"
        elif output_format == "html":
            # HTML直接保存到文件
            result.document.save_as_html(output_path)
            info_msg = f"已导出HTML: {output_path}"
            content = f"已保存HTML到: {output_path}"
        elif output_format == "json":
            # JSON需要导出dict然后序列化
            import json
            content = json.dumps(result.document.export_to_dict(), ensure_ascii=False, indent=2)
            info_msg = f"导出JSON，长度: {len(content)}字符"
        else:
            content = result.document.export_to_markdown()
            info_msg = f"默认导出Markdown，长度: {len(content)}字符"
        
        yield {"type": "info", "message": info_msg}
        logger.debug(info_msg)
            
        # 保存到文件
        if output_format != "html":  # HTML已经直接保存了
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        success_msg = f"已保存到文件: {output_path}"
        yield {"type": "info", "message": success_msg}
        logger.debug(success_msg)
        
        # 提供处理结果
        yield {
            "type": "result", 
            "success": True, 
            "content": content,
            "output_path": output_path,
            "content_type": content_type,
            "conversion_status": str(result.status)
        }
    else:
        error_msg = "文档处理未生成可用文档对象"
        yield {"type": "error", "message": error_msg}
        logger.error(error_msg)
        
        # 如果有错误信息，输出错误信息
        if hasattr(result, 'errors') and result.errors:
            for i, error in enumerate(result.errors):
                error_detail = f"错误 {i+1}: {error}"
                yield {"type": "error", "message": error_detail}
                logger.error(error_detail)
        
        # 提供处理结果（失败）
        yield {
            "type": "result", 
            "success": False,
            "content": "",
            "output_path": output_path,
            "conversion_status": str(result.status)
        }

