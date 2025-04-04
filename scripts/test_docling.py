"""文档处理测试脚本

测试文档加载、处理和分块功能
"""

import argparse
import logging
import asyncio
from pathlib import Path
from typing import Optional

from illufly.docling import (
    DocumentProcessStage,
    DocumentProcessStatus,
    ObservablePipeline,
    ObservablePdfPipeline,
    DocumentLoader,
    DocumentChunker,
    SimpleTextChunker
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def monitor_document_processing(status_tracker: DocumentProcessStatus):
    """监控文档处理进度"""
    try:
        while not status_tracker.completed and not status_tracker.failed and not status_tracker.cancelled:
            # 显示当前处理阶段和进度
            stage = status_tracker.current_stage
            progress = status_tracker.current_progress
            message = status_tracker.current_message
            
            # 根据处理阶段显示不同信息
            if stage == DocumentProcessStage.INITIALIZED:
                logger.info(f"文档处理初始化: {message}")
            elif stage == DocumentProcessStage.DOWNLOADING:
                logger.info(f"下载进度: {progress:.1%} - {message}")
            elif stage == DocumentProcessStage.LOADING:
                logger.info(f"加载进度: {progress:.1%} - {message}")
            elif stage == DocumentProcessStage.BUILDING:
                logger.info(f"构建进度: {progress:.1%} - {message}")
            elif stage == DocumentProcessStage.ASSEMBLING:
                logger.info(f"组装进度: {progress:.1%} - {message}")
            elif stage == DocumentProcessStage.ENRICHING:
                logger.info(f"富化进度: {progress:.1%} - {message}")
            elif stage == DocumentProcessStage.EXPORTING:
                logger.info(f"导出进度: {progress:.1%} - {message}")
            
            await asyncio.sleep(1.0)
        
        # 显示最终结果
        if status_tracker.completed:
            logger.info(f"文档处理完成: {status_tracker.current_message}")
        elif status_tracker.failed:
            logger.error(f"文档处理失败: {status_tracker.error_message}")
        elif status_tracker.cancelled:
            logger.info("文档处理已取消")
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"监控任务异常: {str(e)}")

async def process_document(source: str, chunk_size: Optional[int] = None, overlap: Optional[int] = None):
    """处理文档
    
    Args:
        source: 文档源（文件路径或URL）
        chunk_size: 分块大小
        overlap: 重叠大小
    """
    # 创建状态追踪器
    status_tracker = DocumentProcessStatus()
    
    try:
        # 创建文档加载器
        loader = DocumentLoader(status_tracker)
        
        # 加载文档
        in_doc, format_type = loader.load_document(source)
        
        # 如果是URL，先下载
        if format_type == 'url':
            source = loader.download_document(source)
            in_doc, format_type = loader.load_document(source)
        
        # 根据格式选择处理管道
        if format_type == 'pdf':
            pipeline = ObservablePdfPipeline(
                pipeline_options=None,  # 使用默认选项
                status_tracker=status_tracker
            )
        else:
            pipeline = ObservablePipeline(status_tracker)
        
        # 启动监控任务
        monitor_task = asyncio.create_task(monitor_document_processing(status_tracker))
        
        # 处理文档
        conv_res = pipeline.execute(in_doc, raises_on_error=True)
        
        # 取消监控任务
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        if conv_res.status == 'success':
            # 创建分块器
            chunker = DocumentChunker(
                SimpleTextChunker(
                    chunk_size=chunk_size or 1000,
                    overlap=overlap or 200
                )
            )
            
            # 分块文档
            chunks = chunker.chunk_document(
                conv_res.output.text,
                conv_res.output.metadata
            )
            
            # 显示分块结果
            logger.info(f"文档分块完成，共{len(chunks)}块")
            for i, chunk in enumerate(chunks):
                logger.info(f"分块 {i+1}:")
                logger.info(f"  内容长度: {len(chunk.content)}")
                logger.info(f"  起始位置: {chunk.start_index}")
                logger.info(f"  结束位置: {chunk.end_index}")
                logger.info(f"  内容预览: {chunk.content[:100]}...")
                
        else:
            logger.error(f"文档处理失败: {conv_res.status}")
            
    except Exception as e:
        logger.error(f"文档处理异常: {str(e)}")
        status_tracker.fail(str(e))

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='文档处理测试')
    parser.add_argument('--source', type=str, required=True, help='文档源（文件路径或URL）')
    parser.add_argument('--chunk_size', type=int, help='分块大小')
    parser.add_argument('--overlap', type=int, help='重叠大小')
    
    args = parser.parse_args()
    
    asyncio.run(process_document(args.source, args.chunk_size, args.overlap))

if __name__ == '__main__':
    main() 