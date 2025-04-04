from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import PictureDescriptionApiOptions, PipelineOptions
import os
import sys
import time
import mimetypes
import logging
from pathlib import Path
from dotenv import load_dotenv
import argparse

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mydocling")

# 加载环境变量
load_dotenv()

def detect_file_format(source):
    """检测文件格式"""
    if "://" in source:  # URL
        if source.lower().endswith('.pdf'):
            return 'PDF'
        elif source.lower().endswith(('.doc', '.docx')):
            return 'WORD'
        elif source.lower().endswith(('.html', '.htm')):
            return 'HTML'
        elif source.lower().endswith('.txt'):
            return 'TEXT'
        else:
            return '未知 (URL)'
    else:  # 本地文件
        file_path = Path(source)
        if not file_path.exists():
            return '文件不存在'
        
        # 基于文件扩展名
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            return 'PDF'
        elif ext in ['.doc', '.docx']:
            return 'WORD'
        elif ext in ['.html', '.htm']:
            return 'HTML'
        elif ext == '.txt':
            return 'TEXT'
        
        # 基于文件头
        try:
            with open(source, 'rb') as f:
                header = f.read(8)
                if header.startswith(b'%PDF'):
                    return 'PDF'
                elif header.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
                    return 'DOC'
                elif header.startswith(b'PK'):
                    return 'DOCX/XLSX/ZIP'
        except Exception as e:
            logger.error(f"文件头检测失败: {e}")
        
        # 基于MIME类型
        mime_type, _ = mimetypes.guess_type(source)
        if mime_type:
            if mime_type == 'application/pdf':
                return 'PDF'
            elif mime_type in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                return 'WORD'
            elif mime_type in ['text/html']:
                return 'HTML'
            elif mime_type.startswith('text/'):
                return 'TEXT'
            return f'MIME: {mime_type}'
        
        return '未能识别'

def main():
    # 检查命令行参数
    parser = argparse.ArgumentParser(description="使用Docling处理文档")
    parser.add_argument("source", help="文档路径或URL")
    parser.add_argument("--disable-image-description", "-d", action="store_true", 
                      help="禁用图片描述功能（避免模型加载错误）")
    parser.add_argument("--api-only", "-a", action="store_true",
                      help="只使用API模式处理图片，不使用VLM模型")
    args = parser.parse_args()
    
    source = args.source
    print(f"文档来源: {source}")
    
    # 检测文件格式
    file_format = detect_file_format(source)
    print(f"检测到的文件格式: {file_format}")
    
    # 文件统计信息
    if "://" not in source and Path(source).exists():  # 本地文件
        file_path = Path(source)
        file_size = file_path.stat().st_size / (1024 * 1024)  # MB
        print(f"文件大小: {file_size:.2f}MB")
    
    # 创建pipeline选项
    pipeline_options = PipelineOptions()
    
    # 启用远程服务连接
    pipeline_options.enable_remote_services = True
    
    # 配置图片描述选项
    if args.disable_image_description:
        print("已禁用图片描述功能")
        # 显式禁用图片描述以避免模型加载
        pipeline_options.disable_picture_descriptions = True
    elif args.api_only and os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL"):
        print("仅使用API配置图片描述...")
        # 使用API方式处理图片
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
    elif os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL"):
        print("配置图片描述API (默认)...")
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
    
    print(f"开始转换文档 [{source}]...")
    start_time = time.time()
    
    # 创建一个监控线程来显示进度
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
        print("\n初始化DocumentConverter...")
        
        # 执行转换
        print("开始文档转换...")
        result = converter.convert(source, options=pipeline_options)
        
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
        output_file = f"{Path(source).stem if '://' not in source else 'output'}_docling.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(md_output)
        print(f"完整内容已保存到: {output_file}")
        
    except Exception as e:
        # 停止进度监控
        progress_running = False
        if progress_thread.is_alive():
            progress_thread.join()
        
        print(f"\n\n❌ 文档转换失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()