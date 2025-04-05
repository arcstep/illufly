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

# 创建日志处理器
logger = logging.getLogger("illufly.docling.cli")

# 进度条字符
PROGRESS_CHARS = ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
PROGRESS_BAR_WIDTH = 40

def format_progress_bar(progress: float) -> str:
    """格式化进度条
    
    Args:
        progress: 0-1之间的进度值
        
    Returns:
        格式化后的进度条字符串
    """
    # 确保进度在0-1之间
    progress = max(0.0, min(1.0, progress))
    
    # 计算填充的块数
    filled_width = int(PROGRESS_BAR_WIDTH * progress)
    
    # 计算部分填充字符的索引
    remainder = (PROGRESS_BAR_WIDTH * progress) - filled_width
    partial_idx = min(int(remainder * len(PROGRESS_CHARS)), len(PROGRESS_CHARS) - 1)
    
    # 构建进度条
    bar = '█' * filled_width
    if filled_width < PROGRESS_BAR_WIDTH:
        bar += PROGRESS_CHARS[partial_idx]
        bar += ' ' * (PROGRESS_BAR_WIDTH - filled_width - 1)
    
    return f"[{bar}] {progress*100:.1f}%"

def setup_logging(verbose: bool, quiet: bool, use_original_converter: bool):
    """设置日志配置，分离文件日志和控制台日志
    
    Args:
        verbose: 是否显示详细日志
        quiet: 是否静默模式
        use_original_converter: 是否使用原始转换器
    """
    # 创建根日志记录器
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # 清除现有处理器
    
    # 设置illufly日志级别
    illufly_logger = logging.getLogger("illufly")
    
    # 根据选项设置日志级别
    if verbose:
        illufly_logger.setLevel(logging.DEBUG)
        console_level = logging.INFO if not quiet else logging.WARNING
        
        # 设置docling日志级别（仅在使用原始转换器时）
        if use_original_converter:
            logging.getLogger("docling").setLevel(logging.DEBUG)
    elif quiet:
        illufly_logger.setLevel(logging.ERROR)
        console_level = logging.ERROR
        
        # 设置docling日志级别（仅在使用原始转换器时）
        if use_original_converter:
            logging.getLogger("docling").setLevel(logging.ERROR)
    else:
        illufly_logger.setLevel(logging.INFO)
        console_level = logging.WARNING  # 控制台默认仅显示WARNING以上
        
        # 设置docling日志级别
        if use_original_converter:
            logging.getLogger("docling").setLevel(logging.INFO)
    
    # 创建两个处理器：一个用于控制台，一个用于文件
    # 1. 控制台处理器 - 较高级别，避免干扰进度条
    console_handler = logging.StreamHandler(sys.stderr)  # 使用stderr而非stdout
    console_handler.setLevel(console_level)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    
    # 2. 文件处理器 - 详细日志
    try:
        log_dir = Path.home() / ".illufly" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"docling_{datetime.datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # 文件中保存所有级别日志
        file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        
        # 添加文件处理器
        root_logger.addHandler(file_handler)
        logger.debug(f"日志文件位置: {log_file}")
    except Exception as e:
        # 如果无法创建文件日志，仅使用控制台
        logger.warning(f"无法创建日志文件: {str(e)}")
    
    # 添加控制台处理器
    root_logger.addHandler(console_handler)
    
    # 设置根日志级别为最低，让处理器控制显示
    root_logger.setLevel(logging.DEBUG)

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
    parser.add_argument("--backend", choices=["stable", "standard", "auto"], default="auto",
                        help="后端选择 (默认: auto)")
    
    # 转换器选择参数
    parser.add_argument("-O", "--original", action="store_true", 
                        help="使用官方DocumentConverter而非ObservableConverter")
    
    # 日志控制参数
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志")
    parser.add_argument("-q", "--quiet", action="store_true", help="仅显示错误日志")
    parser.add_argument("--log-file", help="指定日志文件路径")
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging(args.verbose, args.quiet, args.original)
    
    # 追踪处理状态
    success = False
    current_progress_line = ""
    last_stage = None
    
    try:
        # 异步处理文档，接收流式更新
        async for update in process_document(
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
        ):
            # 根据更新类型进行处理
            if "type" not in update:
                continue
                
            update_type = update["type"]
            
            # 信息类型直接打印
            if update_type == "info":
                # 清除可能存在的进度条
                if current_progress_line:
                    sys.stdout.write("\r" + " " * len(current_progress_line) + "\r")
                    current_progress_line = ""
                    
                print(f"➔ {update['message']}")
                
            # 进度类型，更新进度条
            elif update_type == "progress":
                stage = update.get("stage", "")
                progress = update.get("progress", 0.0)
                message = update.get("message", "")
                elapsed = update.get("elapsed", 0.0)
                
                # 阶段变化时打印新阶段
                if stage != last_stage:
                    # 清除当前进度条
                    if current_progress_line:
                        sys.stdout.write("\r" + " " * len(current_progress_line) + "\r")
                        current_progress_line = ""
                    
                    # 打印新阶段
                    print(f"→ 阶段: {stage}")
                    last_stage = stage
                
                # 构建进度条
                progress_bar = format_progress_bar(progress)
                progress_info = f"{progress_bar} | {elapsed:.1f}s | {message}"
                
                # 确保当前行首先被清除
                if current_progress_line:
                    sys.stdout.write("\r" + " " * len(current_progress_line))
                
                # 更新进度条
                sys.stdout.write("\r" + progress_info)
                sys.stdout.flush()
                current_progress_line = progress_info
                
            # 错误类型，打印错误信息
            elif update_type == "error":
                # 清除可能存在的进度条
                if current_progress_line:
                    sys.stdout.write("\r" + " " * len(current_progress_line) + "\r")
                    current_progress_line = ""
                    
                print(f"❌ 错误: {update['message']}")
                
            # 结果类型，处理最终结果
            elif update_type == "result":
                # 清除可能存在的进度条
                if current_progress_line:
                    sys.stdout.write("\r" + " " * len(current_progress_line) + "\r")
                    current_progress_line = ""
                
                success = update.get("success", False)
                if success:
                    print(f"✅ 文档处理成功!")
                    print(f"📄 输出文件: {update.get('output_path', '')}")
                    
                    # 显示内容预览
                    content = update.get('content', '')
                    if content and len(content) > 200:
                        preview = content[:200] + "..."
                        print(f"\n内容预览 (前200字符):\n{preview}")
                else:
                    print(f"❌ 文档处理失败: {update.get('conversion_status', '未知错误')}")
        
        # 最后打印一个换行，确保下一行命令不会紧跟在进度条之后
        print()
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
        
    # 根据处理结果设置退出码
    sys.exit(0 if success else 1)


def main():
    """入口函数"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断操作")
        sys.exit(1)


if __name__ == "__main__":
    main() 