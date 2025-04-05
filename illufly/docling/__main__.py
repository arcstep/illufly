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
from illufly.docling import process_document

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("illufly.docling.cli")

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