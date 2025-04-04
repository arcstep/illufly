#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path
import time

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from illufly.rocksdb import IndexedRocksDB
from illufly.llm.document_manager import DocumentProcessor, DocumentProcessStage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def monitor_document_processing(processor, user_id, doc_id, interval=0.5):
    """监控文档处理进度"""
    print(f"\n开始监控文档处理进度 [{doc_id}]...")
    
    prev_stage = None
    last_pages_processed = 0
    last_preview_time = time.time()
    preview_interval = 3.0  # 每3秒显示一次文本预览
    displayed_models = False  # 是否已显示过模型信息
    
    # 启动时间
    start_time = time.time()
    check_count = 0
    
    while True:
        check_count += 1
        # 获取当前状态
        status = await processor.get_status(user_id, doc_id)
        if not status:
            print(f"找不到文档处理状态: {doc_id}")
            break
        
        # 获取中间结果（如果有）
        intermediate_results = await processor.get_intermediate_results(user_id, doc_id)
        
        # 定期打印更详细的调试信息
        if check_count % 20 == 0:  # 大约每10秒
            if intermediate_results and "intermediate_results" in intermediate_results:
                logger.debug(f"中间结果状态: {intermediate_results['intermediate_results'].get('processing_status', 'unknown')}")
                logger.debug(f"页面进度: {intermediate_results['intermediate_results'].get('pages_processed', 0)}/{intermediate_results['intermediate_results'].get('total_pages', 0)}")
        
        # 打印阶段变化
        if prev_stage != status.stage:
            print(f"\n==== 进入新阶段: {status.stage} ====")
            prev_stage = status.stage
            
            # 如果是初始阶段，显示文件格式信息
            if status.stage == DocumentProcessStage.INITIALIZED and intermediate_results:
                file_format = intermediate_results.get("intermediate_results", {}).get("file_format", "未知")
                source_type = intermediate_results.get("intermediate_results", {}).get("source_type", "未知")
                print(f"文件格式: {file_format}")
                print(f"来源类型: {source_type}")
                if source_type == "url":
                    source_url = intermediate_results.get("intermediate_results", {}).get("source_url", "")
                    print(f"来源URL: {source_url}")
                elif source_type == "local":
                    source_path = intermediate_results.get("intermediate_results", {}).get("source_path", "")
                    print(f"本地路径: {source_path}")
        
        # 显示模型使用信息（如果有且尚未显示）
        if not displayed_models and intermediate_results:
            used_models = intermediate_results.get("intermediate_results", {}).get("used_models", [])
            model_download_info = intermediate_results.get("intermediate_results", {}).get("model_download_info", [])
            
            if used_models:
                print("\n使用的模型:")
                for model in used_models:
                    print(f"  - {model}")
                displayed_models = True
            
            if model_download_info:
                print("\n模型下载信息:")
                for info in model_download_info:
                    print(f"  - {info}")
                displayed_models = True
        
        # 打印进度条
        progress_bar = "=" * int(status.progress * 30)
        elapsed = time.time() - start_time
        progress_info = f"\r进度: [{progress_bar:<30}] {status.progress:.1%} - {status.message} (已运行{int(elapsed)}秒)"
        
        # 添加页面处理信息（如果有）
        pages_info = ""
        if intermediate_results and "pages_processed" in intermediate_results and "total_pages" in intermediate_results:
            pages_processed = intermediate_results["pages_processed"]
            total_pages = intermediate_results["total_pages"]
            
            if total_pages > 0:
                pages_info = f" | 页面: {pages_processed}/{total_pages}"
                
                # 如果页面处理数有变化，打印一次完整信息
                if pages_processed > last_pages_processed:
                    last_pages_processed = pages_processed
                    print(f"\n已处理页面: {pages_processed}/{total_pages} ({pages_processed/total_pages*100:.1f}%)")
                    
                    # 如果有最新处理的段落，显示它
                    if "intermediate_results" in intermediate_results:
                        page_texts = intermediate_results["intermediate_results"].get("page_texts", [])
                        if page_texts and len(page_texts) > last_pages_processed - 1:
                            latest_text = page_texts[last_pages_processed - 1]
                            preview = latest_text[:200] + "..." if len(latest_text) > 200 else latest_text
                            print(f"\n最新处理内容:\n{preview}\n")
        
        # 显示进度信息
        print(f"{progress_info}{pages_info}", end="", flush=True)
        
        # 定期显示文本预览
        current_time = time.time()
        if intermediate_results and "current_text_preview" in intermediate_results and current_time - last_preview_time >= preview_interval:
            preview_text = intermediate_results["current_text_preview"]
            if preview_text:
                # 截取前200个字符作为预览
                preview = preview_text[:200] + "..." if len(preview_text) > 200 else preview_text
                print(f"\n\n文本预览:\n{preview}\n")
                last_preview_time = current_time
        
        # 检查处理状态信息
        if intermediate_results and "intermediate_results" in intermediate_results:
            processing_status = intermediate_results["intermediate_results"].get("processing_status", "")
            if processing_status == "parsing_with_docling":
                print(f"\n当前处理状态: 使用docling解析中...", end="", flush=True)
        
        # 检查是否完成或失败
        if status.stage in [DocumentProcessStage.COMPLETED, DocumentProcessStage.FAILED]:
            if status.stage == DocumentProcessStage.COMPLETED:
                print(f"\n\n✅ 文档处理完成! 耗时: {status.duration:.1f}秒")
            else:
                print(f"\n\n❌ 文档处理失败: {status.error}")
            break
            
        # 等待一段时间再查询
        await asyncio.sleep(interval)
    
    # 处理完成后，获取内容
    if status.stage == DocumentProcessStage.COMPLETED:
        content = await processor.get_document_content(user_id, doc_id)
        if content:
            print(f"\n文档内容预览 (前500字符):\n{content[:500]}...\n")
            # 保存完整内容到文件
            output_file = f"/tmp/{doc_id}_content.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"完整内容已保存到: {output_file}")
            
            # 如果有中间结果，显示文档结构信息
            if intermediate_results and "intermediate_results" in intermediate_results:
                doc_structure = intermediate_results["intermediate_results"].get("document_structure", {})
                if doc_structure:
                    print("\n文档结构信息:")
                    for key, value in doc_structure.items():
                        print(f"  - {key}: {value}")
        else:
            print("\n未能获取文档内容")

async def main():
    parser = argparse.ArgumentParser(description="测试文档处理器")
    parser.add_argument("--source", "-s", required=True, help="文档路径或URL")
    parser.add_argument("--user", "-u", default="test_user", help="用户ID")
    parser.add_argument("--db_path", "-d", default="/tmp/illufly_test_db", help="RocksDB路径")
    parser.add_argument("--cancel_after", "-c", type=int, default=0, help="几秒后取消处理 (0表示不取消)")
    parser.add_argument("--interval", "-i", type=float, default=0.5, help="轮询状态的间隔时间(秒)")
    args = parser.parse_args()
    
    # 确认文件存在或URL有效
    if "://" not in args.source and not os.path.exists(args.source):
        logger.error(f"文件不存在: {args.source}")
        return
    
    # 打印源文件信息
    if "://" in args.source:
        logger.info(f"将处理网络URL: {args.source}")
    else:
        file_path = Path(args.source)
        file_size = file_path.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"将处理本地文件: {args.source}, 大小: {file_size:.2f}MB")
        
        # 尝试初步判断文件类型
        try:
            with open(args.source, 'rb') as f:
                header = f.read(8)
                if header.startswith(b'%PDF'):
                    logger.info("文件类型检测: PDF")
                elif header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
                    logger.info("文件类型检测: DOC")
                elif header.startswith(b'PK'):
                    logger.info("文件类型检测: DOCX/XLSX/ZIP")
                else:
                    # 检查是否为文本文件
                    try:
                        with open(args.source, 'r', encoding='utf-8') as f_text:
                            content = f_text.read(100)
                            if '<html' in content.lower():
                                logger.info("文件类型检测: HTML")
                            else:
                                logger.info("文件类型检测: 可能是文本文件")
                    except UnicodeDecodeError:
                        logger.info("文件类型检测: 二进制文件，无法确定具体类型")
        except Exception as e:
            logger.warning(f"文件类型检测失败: {e}")
    
    # 初始化数据库
    db_path = Path(args.db_path)
    db_path.mkdir(exist_ok=True, parents=True)
    db = IndexedRocksDB(str(db_path))
    
    # 初始化文档处理器
    processor = DocumentProcessor(db)
    
    logger.info(f"开始异步文档处理流程...")
    # 启动文档处理
    doc_id, status = await processor.process_document(args.user, args.source)
    logger.info(f"已启动文档处理任务: {args.source} (ID: {doc_id})")
    
    # 如果设置了取消时间
    if args.cancel_after > 0:
        async def cancel_task():
            logger.info(f"计划在 {args.cancel_after} 秒后取消处理...")
            await asyncio.sleep(args.cancel_after)
            logger.info(f"开始取消文档处理 [{doc_id}]...")
            result = await processor.cancel_processing(args.user, doc_id)
            logger.info(f"取消结果: {'成功' if result else '失败'}")
        
        # 创建取消任务
        asyncio.create_task(cancel_task())
    
    # 监控处理进度
    await monitor_document_processing(processor, args.user, doc_id, interval=args.interval)

if __name__ == "__main__":
    asyncio.run(main()) 