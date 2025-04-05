#!/usr/bin/env python3
"""
Illufly docling CLI - 文档转换工具

按照官方docling风格实现的命令行工具，同时增加异步进度监测。
支持切换为官方DocumentConverter以便对比测试。
"""

import argparse
import asyncio
import logging
import os
import sys
import datetime
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

# 导入本地组件
from illufly.docling import ObservableConverter, DocumentProcessStage

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
logger = logging.getLogger("illufly.docling.cli")


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
) -> bool:
    """异步处理文档并实时监控进度

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

    Returns:
        处理成功返回True，否则返回False
    """
    try:
        # 确定输入路径
        if not source.startswith(('http://', 'https://')) and not os.path.exists(source):
            logger.error(f"文件不存在: {source}")
            return False

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
        
        logger.info(f"处理文档: {source}")
        logger.info(f"输出路径: {output_path}")
        
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
            logger.info("使用官方DocumentConverter")
            return await process_with_original_converter(
                source=source,
                format_options=format_options,
                output_format=output_format,
                output_path=output_path
            )
        else:
            logger.info("使用自定义ObservableConverter")
            return await process_with_observable_converter(
                source=source,
                format_options=format_options,
                output_format=output_format,
                output_path=output_path
            )
            
    except Exception as e:
        logger.error(f"处理文档出错: {str(e)}", exc_info=True)
        return False


async def process_with_original_converter(
    source: str,
    format_options: Dict[InputFormat, Any],
    output_format: str = "markdown",
    output_path: Optional[str] = None
) -> bool:
    """使用官方DocumentConverter处理文档
    
    Args:
        source: 源文件路径或URL
        format_options: 格式选项
        output_format: 输出格式
        output_path: 输出路径
        
    Returns:
        处理成功返回True，否则返回False
    """
    # 创建官方转换器
    converter = DocumentConverter(format_options=format_options)
    
    # 使用线程池执行同步转换
    loop = asyncio.get_running_loop()
    start_time = time.time()
    
    logger.info("开始同步转换文档...")
    try:
        # 执行转换（在线程池中运行避免阻塞事件循环）
        result = await loop.run_in_executor(
            None, 
            lambda: converter.convert(source, raises_on_error=False)
        )
        
        # 计算耗时
        elapsed = time.time() - start_time
        logger.info(f"文档处理完成! 总耗时: {elapsed:.2f}秒, 状态: {result.status}")
        
        # 生成输出
        if result.status in [ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS] and result.document:
            if output_format == "markdown":
                content = result.document.export_to_markdown()
                logger.info(f"导出Markdown，长度: {len(content)}字符")
            elif output_format == "text":
                content = result.document.export_to_text()
                logger.info(f"导出纯文本，长度: {len(content)}字符")
            elif output_format == "html":
                # HTML直接保存到文件
                result.document.save_as_html(output_path)
                logger.info(f"已导出HTML: {output_path}")
                return True
            elif output_format == "json":
                # JSON需要导出dict然后序列化
                import json
                content = json.dumps(result.document.export_to_dict(), ensure_ascii=False, indent=2)
                logger.info(f"导出JSON，长度: {len(content)}字符")
            else:
                content = result.document.export_to_markdown()
                logger.info(f"默认导出Markdown，长度: {len(content)}字符")
                
            # 保存到文件
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
                
            logger.info(f"已保存到文件: {output_path}")
            return True
        else:
            logger.error(f"文档处理失败: {result.status}")
            # 如果有错误信息，输出错误信息
            if hasattr(result, 'errors') and result.errors:
                for i, error in enumerate(result.errors):
                    logger.error(f"错误 {i+1}: {error}")
            return False
    
    except Exception as e:
        logger.error(f"使用官方转换器处理文档时出错: {str(e)}", exc_info=True)
        return False


async def process_with_observable_converter(
    source: str,
    format_options: Dict[InputFormat, Any],
    output_format: str = "markdown",
    output_path: Optional[str] = None
) -> bool:
    """使用自定义ObservableConverter处理文档
    
    Args:
        source: 源文件路径或URL
        format_options: 格式选项
        output_format: 输出格式
        output_path: 输出路径
        
    Returns:
        处理成功返回True，否则返回False
    """
    # 创建可观测转换器
    converter = ObservableConverter(format_options=format_options)
    
    # 开始异步处理
    start_time = datetime.datetime.now()
    last_progress = 0
    last_stage = None
    
    # 收集所有更新
    updates = []
    result = None
    
    # 异步转换文档，并获取实时更新
    async for update in converter.convert_async(source, raises_on_error=False):
        updates.append(update)
        
        # 处理状态更新
        if isinstance(update, dict):
            if "stage" in update:
                # 处理阶段更新
                stage = update.get("stage")
                progress = update.get("progress", 0) * 100
                message = update.get("message", "")
                
                # 只在阶段或进度变化时打印
                if stage != last_stage or int(progress) > int(last_progress) + 4:
                    elapsed = (datetime.datetime.now() - start_time).total_seconds()
                    logger.info(f"阶段: {stage} | 进度: {progress:.0f}% | 耗时: {elapsed:.1f}秒 | {message}")
                    last_stage = stage
                    last_progress = progress
                
            # 处理最终结果
            elif "type" in update and update["type"] == "result":
                result = update.get("result")
    
    # 检查处理状态
    if not result:
        logger.error("文档处理未返回结果")
        return False
    
    # 计算总耗时
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    logger.info(f"文档处理完成! 总耗时: {elapsed:.2f}秒, 状态: {result.status}")
    
    # 根据输出格式导出内容
    if result.document:
        if output_format == "markdown":
            content = result.document.export_to_markdown()
            logger.info(f"导出Markdown，长度: {len(content)}字符")
        elif output_format == "text":
            content = result.document.export_to_text()
            logger.info(f"导出纯文本，长度: {len(content)}字符")
        elif output_format == "html":
            # HTML直接保存到文件
            result.document.save_as_html(output_path)
            logger.info(f"已导出HTML: {output_path}")
            return True
        elif output_format == "json":
            # JSON需要导出dict然后序列化
            import json
            content = json.dumps(result.document.export_to_dict(), ensure_ascii=False, indent=2)
            logger.info(f"导出JSON，长度: {len(content)}字符")
        else:
            content = result.document.export_to_markdown()
            logger.info(f"默认导出Markdown，长度: {len(content)}字符")
            
        # 保存到文件
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.info(f"已保存到文件: {output_path}")
        return True
    else:
        logger.error("文档处理未生成可用文档对象")
        # 如果有错误信息，输出错误信息
        if hasattr(result, 'errors') and result.errors:
            for i, error in enumerate(result.errors):
                logger.error(f"错误 {i+1}: {error}")
        return False


async def main_async():
    """异步主函数"""
    parser = argparse.ArgumentParser(description="文档转换工具 - 支持PDF、Word、HTML等格式")
    
    # 文档输入输出参数
    parser.add_argument("source", help="源文件路径或URL")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("-f", "--format", choices=["markdown", "text", "html", "json"], 
                      default="markdown", help="输出格式 (默认: markdown)")
    
    # 功能控制参数
    parser.add_argument("--remote", action="store_true", help="启用远程服务")
    parser.add_argument("--ocr", action="store_true", help="启用OCR")
    parser.add_argument("--tables", action="store_true", help="启用表格检测")
    parser.add_argument("--formulas", action="store_true", help="启用公式检测")
    parser.add_argument("--describe-pictures", action="store_true", help="启用图片描述")
    parser.add_argument("--backend", choices=["stable", "standard", "auto"], default="stable",
                      help="后端选择 (默认: stable)")
    
    # 转换器选择参数
    parser.add_argument("-O", "--original", action="store_true", 
                      help="使用官方DocumentConverter而非ObservableConverter")
    
    # 日志控制参数
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅显示错误日志")
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger("illufly").setLevel(logging.DEBUG)
        # 对于官方转换器，也设置docling的日志级别
        if args.original:
            logging.getLogger("docling").setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger("illufly").setLevel(logging.ERROR)
        # 对于官方转换器，也设置docling的日志级别
        if args.original:
            logging.getLogger("docling").setLevel(logging.ERROR)
    
    # 处理文档
    success = await process_document(
        source=args.source,
        output_format=args.format,
        output_path=args.output,
        enable_remote_services=args.remote,
        do_ocr=args.ocr,
        do_table_detection=args.tables,
        do_formula_detection=args.formulas,
        enable_pic_description=args.describe_pictures,
        backend_choice=args.backend,
        use_original_converter=args.original
    )
    
    sys.exit(0 if success else 1)


def main():
    """入口函数"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(1)


if __name__ == "__main__":
    main() 