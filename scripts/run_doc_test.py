#!/usr/bin/env python3
"""
集成测试脚本：测试文档处理功能
同时测试直接使用docling和通过DocumentProcessor处理文档
"""

import os
import sys
import time
import asyncio
import argparse
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("doc-test")

# 确保能找到illufly模块
sys.path.append(str(Path(__file__).parent.parent))

# 设置环境变量以禁用可能出错的功能
os.environ["DOCLING_DISABLE_VLM"] = "1"  # 禁用VLM模型加载

async def test_direct_docling(source_path, disable_image_description=True):
    """直接使用docling库处理文档"""
    logger.info("=== 测试直接使用docling库处理文档 ===")
    
    from docling.document_converter import DocumentConverter
    from docling.datamodel.pipeline_options import PipelineOptions, PictureDescriptionApiOptions
    
    print(f"文档来源: {source_path}")
    print(f"禁用图片描述: {disable_image_description}")
    
    # 检测文件格式
    file_format = ""
    if "://" in source_path:  # URL
        if source_path.lower().endswith('.pdf'):
            file_format = 'PDF'
        elif source_path.lower().endswith(('.doc', '.docx')):
            file_format = 'WORD'
    else:  # 本地文件
        file_path = Path(source_path)
        if not file_path.exists():
            print(f"文件不存在: {source_path}")
            return
        
        try:
            with open(source_path, 'rb') as f:
                header = f.read(8)
                if header.startswith(b'%PDF'):
                    file_format = 'PDF'
                elif header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
                    file_format = 'DOC'
                elif header.startswith(b'PK'):
                    file_format = 'DOCX/XLSX/ZIP'
        except Exception as e:
            logger.error(f"文件头检测失败: {e}")
    
    print(f"检测到的文件格式: {file_format}")
    
    # 创建pipeline选项
    pipeline_options = PipelineOptions()
    
    # 启用远程服务连接
    pipeline_options.enable_remote_services = True
    
    # 根据选项配置图片描述
    if disable_image_description:
        print("禁用图片描述功能")
        pipeline_options.disable_picture_descriptions = True
    elif os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL"):
        print("使用API配置图片描述")
        pipeline_options.picture_description_options = PictureDescriptionApiOptions(
            url=os.getenv("OPENAI_BASE_URL") + "/v1/chat/completions",
            api_key=os.getenv("OPENAI_API_KEY"),
            params=dict(
                model=os.getenv("OPENAI_MODEL_NAME", "gpt-4-vision-preview"),
                seed=42,
                max_completion_tokens=200,
            ),
            prompt="描述图片内容，用三句话概括。请简洁准确。",
            timeout=90,
        )
        # 显式设置使用API而非VLM
        pipeline_options.picture_description_model_name = "api"
    
    print(f"开始转换文档...")
    start_time = time.time()
    
    # 创建进度显示
    import threading
    import sys
    
    progress_running = True
    
    def progress_monitor():
        spinner = ['|', '/', '-', '\\']
        counter = 0
        start = time.time()
        while progress_running:
            elapsed = time.time() - start
            sys.stdout.write(f"\r处理中... {spinner[counter % 4]} 已用时间: {elapsed:.1f}秒")
            sys.stdout.flush()
            counter += 1
            time.sleep(0.2)
    
    # 启动进度监控
    progress_thread = threading.Thread(target=progress_monitor)
    progress_thread.daemon = True
    progress_thread.start()
    
    try:
        # 初始化转换器
        converter = DocumentConverter()
        
        # 执行转换
        result = converter.convert(source_path, options=pipeline_options)
        
        # 停止进度监控
        progress_running = False
        progress_thread.join()
        
        # 显示转换结果
        elapsed_time = time.time() - start_time
        print(f"\n\n✅ 文档转换完成! 耗时: {elapsed_time:.2f}秒")
        
        # 文档结构信息
        doc = result.document
        print(f"\n文档信息:")
        print(f"- 标题: {doc.title or '未提取到标题'}")
        print(f"- 作者: {', '.join(doc.authors) if doc.authors else '未提取到作者'}")
        print(f"- 摘要: {doc.abstract[:100] + '...' if len(doc.abstract) > 100 else doc.abstract or '未提取到摘要'}")
        print(f"- 段落数: {len(doc.paragraphs)}")
        print(f"- 图片数: {len([p for p in doc.paragraphs if p.image])}")
        print(f"- 表格数: {len([p for p in doc.paragraphs if p.table])}")
        
        # 导出为Markdown
        md_output = doc.export_to_markdown()
        print(f"\nMarkdown预览 (前300字符):\n{md_output[:300]}...\n")
        
        # 保存到文件
        output_file = f"{Path(source_path).stem if '://' not in source_path else 'output'}_docling.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_output)
        print(f"完整内容已保存到: {output_file}")
        
        return output_file
        
    except Exception as e:
        # 停止进度监控
        progress_running = False
        if progress_thread.is_alive():
            progress_thread.join()
        
        print(f"\n\n❌ 文档转换失败: {e}")
        import traceback
        traceback.print_exc()
        return None

async def test_processor(source_path, user_id="test_user", db_path="/tmp/doctest_db", disable_image_description=True):
    """使用DocumentProcessor测试文档处理"""
    logger.info("=== 测试使用DocumentProcessor处理文档 ===")
    
    # 设置环境变量禁用图片描述（如果需要）
    if disable_image_description:
        os.environ["DOCLING_DISABLE_PICTURE_DESCRIPTION"] = "1"
    else:
        os.environ["DOCLING_DISABLE_PICTURE_DESCRIPTION"] = "0"
    
    # 导入文档处理相关模块
    from illufly.storage.indexed_rocksdb import IndexedRocksDB
    from illufly.llm.document_manager import (
        DocumentProcessor, 
        DocumentProcessStage,
        DocumentProcessStatus
    )
    
    # 确保数据库目录存在
    db_dir = Path(db_path)
    db_dir.mkdir(exist_ok=True, parents=True)
    
    # 初始化数据库和处理器
    db = IndexedRocksDB(str(db_dir))
    processor = DocumentProcessor(db)
    
    print(f"\n==== 开始处理文档 ====")
    print(f"来源: {source_path}")
    print(f"用户ID: {user_id}")
    print(f"数据库路径: {db_path}")
    print(f"图片处理: {'禁用' if disable_image_description else '启用'}")
    
    # 启动处理
    start_time = time.time()
    doc_id, status = await processor.process_document(user_id, source_path)
    print(f"文档ID: {doc_id}")
    
    # 监控处理进度
    spinner = ['|', '/', '-', '\\']
    counter = 0
    last_preview_time = time.time()
    preview_interval = 3.0  # 每3秒显示一次中间内容
    
    prev_stage = None
    processing_errors = []
    
    while True:
        # 获取当前状态
        status = await processor.get_status(user_id, doc_id)
        if not status:
            print(f"找不到文档处理状态!")
            break
            
        # 获取中间结果
        try:
            intermediate_results = await processor.get_intermediate_results(user_id, doc_id)
        except Exception as e:
            logger.warning(f"获取中间结果时发生错误: {e}")
            intermediate_results = {}
        
        # 显示阶段变化
        if prev_stage != status.stage:
            elapsed = time.time() - start_time
            print(f"\n==== 进入新阶段: {status.stage} [已用时: {elapsed:.1f}秒] ====")
            prev_stage = status.stage
            
            # 显示阶段相关信息
            if status.stage == DocumentProcessStage.INITIALIZED and intermediate_results:
                ir = intermediate_results.get("intermediate_results", {})
                file_format = ir.get("file_format", "未知")
                source_type = ir.get("source_type", "未知")
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
        if (current_time - last_preview_time) >= preview_interval and intermediate_results:
            last_preview_time = current_time
            print("\n")  # 添加换行以分隔进度和预览
            
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
                    output_file = f"/tmp/{Path(source_path).stem if '://' not in source_path else 'doc-'+doc_id}_processor.md"
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"完整内容已保存到: {output_file}")
                    return output_file
                else:
                    print("\n未能获取文档内容")
                    return None
            else:
                print(f"\n\n❌ 文档处理失败: {status.error}")
                return None
            break
        
        # 暂停一段时间
        await asyncio.sleep(0.3)
    
    return None

async def compare_results(direct_output, processor_output):
    """比较两种方法的处理结果"""
    if not direct_output or not processor_output:
        print("\n无法比较结果：至少有一种方法失败了")
        return
    
    print("\n=== 比较处理结果 ===")
    
    # 读取文件内容
    with open(direct_output, 'r', encoding='utf-8') as f:
        direct_content = f.read()
    
    with open(processor_output, 'r', encoding='utf-8') as f:
        processor_content = f.read()
    
    # 基本统计
    direct_size = len(direct_content)
    processor_size = len(processor_content)
    
    print(f"直接使用docling: {direct_size} 字符")
    print(f"使用DocumentProcessor: {processor_size} 字符")
    print(f"大小比例: {processor_size/direct_size:.2f}x")
    
    # 段落数量
    direct_paragraphs = len([p for p in direct_content.split('\n\n') if p.strip()])
    processor_paragraphs = len([p for p in processor_content.split('\n\n') if p.strip()])
    
    print(f"直接使用docling: {direct_paragraphs} 段落")
    print(f"使用DocumentProcessor: {processor_paragraphs} 段落")
    
    # 内容相似度（简单比较）
    import difflib
    similarity = difflib.SequenceMatcher(None, direct_content, processor_content).ratio()
    print(f"内容相似度: {similarity:.2%}")
    
    # 不同点统计
    if similarity < 0.9:
        print("\n主要不同点:")
        d = difflib.Differ()
        diff = list(d.compare(direct_content[:1000].splitlines(), processor_content[:1000].splitlines()))
        diff_lines = [line for line in diff if line.startswith('+ ') or line.startswith('- ')]
        for line in diff_lines[:10]:  # 仅显示前10个不同
            print(line)

async def main():
    parser = argparse.ArgumentParser(description="测试文档处理功能")
    parser.add_argument("source", help="文档路径或URL")
    parser.add_argument("--db_path", "-d", default="/tmp/doctest_db", help="数据库路径")
    parser.add_argument("--user", "-u", default="test_user", help="用户ID")
    parser.add_argument("--enable-image-processing", "-e", action="store_true", 
                        help="启用图片处理功能（默认禁用，避免模型加载错误）")
    parser.add_argument("--method", "-m", choices=["direct", "processor", "both"], 
                        default="both", help="测试方法: direct=直接使用docling, processor=使用DocumentProcessor, both=两者都测试(默认)")
    args = parser.parse_args()
    
    # 检查文件存在或URL有效
    if "://" not in args.source and not Path(args.source).exists():
        print(f"文件不存在: {args.source}")
        return
    
    disable_image_description = not args.enable_image_processing
    
    direct_output = None
    processor_output = None
    
    # 执行测试
    if args.method in ["direct", "both"]:
        direct_output = await test_direct_docling(args.source, disable_image_description)
    
    if args.method in ["processor", "both"]:
        processor_output = await test_processor(args.source, args.user, args.db_path, disable_image_description)
    
    # 如果两种方法都测试了，比较结果
    if args.method == "both" and direct_output and processor_output:
        await compare_results(direct_output, processor_output)

if __name__ == "__main__":
    asyncio.run(main()) 