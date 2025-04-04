#!/usr/bin/env python3
"""
测试Docling的PDF处理功能和进度跟踪
专注于PDF格式的检测、识别和处理过程中的实时进度反馈
"""

import os
import sys
import asyncio
import logging
import time
import argparse
import json
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test-pdf")

# 确保能找到illufly模块
sys.path.append(str(Path(__file__).parent.parent))

# 导入需要的模块
from illufly.llm.document_manager import (
    DocumentProcessor, 
    DocumentProcessStage,
    DocumentProcessStatus
)
from illufly.storage.indexed_rocksdb import IndexedRocksDB

# 配置环境
os.environ["DOCLING_DISABLE_VLM"] = "1"  # 禁用默认的VLM模型加载

async def test_pdf_detection():
    """测试PDF格式检测功能"""
    from illufly.llm.document_manager import DocumentManager
    
    # 测试URL
    url_tests = [
        "https://arxiv.org/pdf/2408.09869.pdf",
        "https://arxiv.org/pdf/2503.21760",
        "https://example.com/document.pdf",
        "https://example.com/document.docx",
        "https://example.com/document.txt",
    ]
    
    print("=== 测试URL格式检测 ===")
    for url in url_tests:
        result = DocumentManager._detect_file_format(url)
        print(f"URL: {url} -> 检测格式: {result}")
    
    # 测试本地文件（如果有）
    test_files = [
        "/tmp/test.pdf",
        "/tmp/test.docx",
        "/tmp/test.txt",
    ]
    
    print("\n=== 测试本地文件格式检测 ===")
    for file_path in test_files:
        if Path(file_path).exists():
            result = DocumentManager._detect_file_format(file_path)
            print(f"文件: {file_path} -> 检测格式: {result}")
        else:
            print(f"文件不存在: {file_path} (跳过)")

async def safe_get_intermediate_results(processor, user_id, doc_id):
    """安全获取中间结果，处理可能的序列化问题"""
    try:
        return await processor.get_intermediate_results(user_id, doc_id)
    except Exception as e:
        logger.warning(f"获取中间结果时发生错误: {e}")
        return {}

async def configure_document_processor(db):
    """配置文档处理器，禁用可能导致错误的功能"""
    processor = DocumentProcessor(db)
    
    # 通过反射访问内部属性配置docling选项
    if hasattr(processor, "_docling_pipeline_options"):
        # 禁用图片描述功能
        processor._docling_pipeline_options.disable_picture_descriptions = True
        logger.info("已禁用图片描述功能以避免模型加载错误")
    
    # 或者通过环境变量禁用
    os.environ["DOCLING_DISABLE_VLM"] = "1"
    os.environ["DOCLING_DISABLE_PICTURE_DESCRIPTION"] = "1"
    
    return processor

async def test_pdf_processing(source, user_id="test_user", db_path="/tmp/illufly_pdf_test_db", disable_image_processing=True):
    """测试PDF处理和进度跟踪"""
    # 确保数据库目录存在
    db_dir = Path(db_path)
    db_dir.mkdir(exist_ok=True, parents=True)
    
    # 初始化数据库和处理器
    db = IndexedRocksDB(str(db_dir))
    processor = await configure_document_processor(db)
    
    print(f"\n==== 开始处理PDF文档 ====")
    print(f"来源: {source}")
    print(f"用户ID: {user_id}")
    print(f"数据库路径: {db_path}")
    print(f"图片处理: {'禁用' if disable_image_processing else '启用'}")
    
    # 检测文件格式
    from illufly.llm.document_manager import DocumentManager
    detected_format = DocumentManager._detect_file_format(source)
    print(f"检测到的文件格式: {detected_format}")
    
    # 启动处理
    start_time = time.time()
    doc_id, status = await processor.process_document(user_id, source)
    print(f"文档ID: {doc_id}")
    
    # 监控处理进度
    spinner = ['|', '/', '-', '\\']
    counter = 0
    last_preview_time = time.time()
    preview_interval = 5.0  # 每5秒显示一次中间内容
    
    prev_stage = None
    processing_errors = []
    
    while True:
        # 获取当前状态
        status = await processor.get_status(user_id, doc_id)
        if not status:
            print(f"找不到文档处理状态!")
            break
            
        # 获取中间结果
        intermediate_results = await safe_get_intermediate_results(processor, user_id, doc_id)
        
        # 显示阶段变化
        if prev_stage != status.stage:
            elapsed = time.time() - start_time
            print(f"\n==== 进入新阶段: {status.stage} [已用时: {elapsed:.1f}秒] ====")
            prev_stage = status.stage
            
            # 显示阶段相关信息
            if status.stage == DocumentProcessStage.INITIALIZED:
                if intermediate_results:
                    file_format = intermediate_results.get("file_format", "未知")
                    source_type = intermediate_results.get("source_type", "未知")
                    print(f"文件格式: {file_format}")
                    print(f"来源: {source_type}")
            
        # 显示进度和消息
        elapsed = time.time() - start_time
        progress_bar = "=" * int(status.progress * 30)
        sys.stdout.write(f"\r[{progress_bar:<30}] {status.progress:.1%} {spinner[counter % 4]} {status.message} [已用时: {elapsed:.1f}秒]")
        sys.stdout.flush()
        counter += 1
        
        # 显示中间结果预览
        current_time = time.time()
        if intermediate_results and (current_time - last_preview_time) >= preview_interval:
            last_preview_time = current_time
            print("\n")  # 添加换行以分隔进度和预览
            
            # 处理中间结果
            if "intermediate_results" in intermediate_results:
                ir = intermediate_results["intermediate_results"]
                
                # 显示处理状态
                processing_status = ir.get("processing_status", "")
                if processing_status:
                    print(f"处理状态: {processing_status}")
                
                # 显示页面处理信息
                pages_processed = ir.get("pages_processed", 0)
                total_pages = ir.get("total_pages", 0)
                
                if total_pages > 0:
                    print(f"页面进度: {pages_processed}/{total_pages} ({pages_processed/total_pages*100:.1f}%)")
                
                # 显示最新处理内容预览
                page_texts = ir.get("page_texts", [])
                if page_texts and len(page_texts) > 0:
                    latest_text = page_texts[-1]
                    preview = latest_text[:200] + "..." if len(latest_text) > 200 else latest_text
                    print(f"最新处理内容:\n{preview}\n")
                
                # 显示当前文本预览
                current_text = ir.get("current_text_preview", "")
                if current_text:
                    preview = current_text[:200] + "..." if len(current_text) > 200 else current_text
                    print(f"当前文本预览:\n{preview}\n")
                
                # 检查是否有错误
                error = ir.get("error", "")
                if error and error not in processing_errors:
                    processing_errors.append(error)
                    print(f"\n⚠️ 处理过程中出现错误: {error}")
        
        # 检查是否完成
        if status.stage in [DocumentProcessStage.COMPLETED, DocumentProcessStage.FAILED]:
            if status.stage == DocumentProcessStage.COMPLETED:
                elapsed = time.time() - start_time
                print(f"\n\n✅ 文档处理完成! 总耗时: {elapsed:.2f}秒")
                
                # 获取处理结果
                content = await processor.get_document_content(user_id, doc_id)
                if content:
                    print(f"\n文档内容预览 (前300字符):\n{content[:300]}...\n")
                    
                    # 保存结果
                    output_file = f"/tmp/{Path(source).stem if '://' not in source else 'doc-'+doc_id}_content.md"
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"完整内容已保存到: {output_file}")
                    
                    # 如果有处理错误，显示汇总
                    if processing_errors:
                        print("\n处理过程中出现的错误:")
                        for i, error in enumerate(processing_errors):
                            print(f"{i+1}. {error}")
            else:
                print(f"\n\n❌ 文档处理失败: {status.error}")
                
                # 尝试保存错误详情
                error_file = f"/tmp/{Path(source).stem if '://' not in source else 'doc-'+doc_id}_error.json"
                try:
                    error_info = {
                        "error": status.error,
                        "stage": status.stage,
                        "progress": status.progress,
                        "message": status.message,
                        "duration": status.duration,
                        "processing_errors": processing_errors,
                        "intermediate_results": intermediate_results.get("intermediate_results", {})
                    }
                    with open(error_file, "w") as f:
                        json.dump(error_info, f, indent=2)
                    print(f"错误详情已保存到: {error_file}")
                except:
                    pass
            break
        
        # 暂停一段时间
        await asyncio.sleep(0.5)

async def main():
    parser = argparse.ArgumentParser(description="测试PDF处理功能")
    parser.add_argument("--source", "-s", help="PDF文档路径或URL")
    parser.add_argument("--db_path", "-d", default="/tmp/illufly_pdf_test_db", help="数据库路径")
    parser.add_argument("--user", "-u", default="test_user", help="用户ID")
    parser.add_argument("--test-detection", "-t", action="store_true", help="只测试格式检测功能")
    parser.add_argument("--enable-image-processing", "-e", action="store_true", 
                       help="启用图片处理功能（默认禁用，避免模型加载错误）")
    args = parser.parse_args()
    
    if args.test_detection:
        await test_pdf_detection()
        return
        
    if not args.source:
        parser.print_help()
        return
    
    await test_pdf_processing(
        args.source, 
        args.user, 
        args.db_path, 
        disable_image_processing=not args.enable_image_processing
    )

if __name__ == "__main__":
    asyncio.run(main()) 