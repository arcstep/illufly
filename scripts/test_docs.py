#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).resolve().parent.parent))

from illufly.upload.base import UploadService, FileStatus
from illufly.llm.docs import DocumentManager, DocumentSource
from illufly.llm.chunking import ChunkingStrategy
from illufly.rocksdb import IndexedRocksDB

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 参数解析
parser = argparse.ArgumentParser(description='文档服务测试脚本')
parser.add_argument('--action', type=str, required=True, 
                    choices=['upload', 'web', 'list', 'search', 'delete'],
                    help='操作类型: upload(上传文件), web(网页抓取), list(列出文档), search(搜索), delete(删除)')
parser.add_argument('--user_id', type=str, default='test_user', help='用户ID')
parser.add_argument('--file', type=str, help='要上传的文件路径')
parser.add_argument('--url', type=str, help='要抓取的网页URL')
parser.add_argument('--doc_id', type=str, help='文档ID')
parser.add_argument('--query', type=str, help='搜索查询')
parser.add_argument('--db_path', type=str, default='./db', help='RocksDB路径')
parser.add_argument('--storage_path', type=str, default='./uploads', help='文件存储路径')
parser.add_argument('--chunk_strategy', type=str, default='simple', 
                    choices=['simple', 'hybrid', 'markdown', 'token'],
                    help='文档切片策略: simple(简单字符切片), hybrid(混合切片), markdown(Markdown优化), token(基于token)')
parser.add_argument('--chunk_size', type=int, default=500, help='切片大小(字符数)')
parser.add_argument('--chunk_overlap', type=int, default=50, help='切片重叠大小(字符数)')
parser.add_argument('--max_tokens', type=int, default=None, help='每个切片最大token数量(用于hybrid/token策略)')

args = parser.parse_args()

# 初始化服务
db = IndexedRocksDB(args.db_path)
file_service = UploadService(args.storage_path)

# 根据参数选择切片策略
chunking_strategy = ChunkingStrategy(args.chunk_strategy)

# 初始化文档管理器
doc_manager = DocumentManager(
    db, 
    file_service,
    chunking_strategy=chunking_strategy,
    chunk_size=args.chunk_size,
    chunk_overlap=args.chunk_overlap
)

async def init_services():
    """初始化服务"""
    # 初始化文件清理任务
    file_service.start_cleanup_task()
    # 初始化检索器
    await doc_manager.init_retriever()
    logger.info(f"服务初始化完成，切片策略: {chunking_strategy.value}")

async def upload_file():
    """上传文件测试"""
    if not args.file:
        logger.error("缺少文件路径参数 --file")
        return
    
    file_path = Path(args.file)
    if not file_path.exists():
        logger.error(f"文件不存在: {file_path}")
        return
    
    # 读取文件内容
    with open(file_path, 'rb') as f:
        file_content = f.read()
    
    # 模拟文件上传对象
    class MockUploadFile:
        def __init__(self, filename, content):
            self.filename = filename
            self.content = content
            self._read_position = 0
        
        async def read(self, size):
            if self._read_position >= len(self.content):
                return b''
            
            chunk = self.content[self._read_position:self._read_position + size]
            self._read_position += size
            return chunk
    
    mock_file = MockUploadFile(file_path.name, file_content)
    
    # 保存文件
    logger.info(f"开始上传文件: {file_path.name}")
    file_info = await file_service.save_file(args.user_id, mock_file)
    
    # 处理文档
    title = file_path.stem
    doc = await doc_manager.process_upload(
        user_id=args.user_id,
        file_info=file_info,
        title=title,
        description=f"从本地上传的文件: {file_path.name}"
    )
    
    logger.info(f"文件上传成功: {doc.id}")
    logger.info(f"文档标题: {doc.title}")
    logger.info(f"文档类型: {doc.type}")
    logger.info(f"切片数量: {doc.chunks_count}")

async def process_web():
    """网页抓取测试"""
    if not args.url:
        logger.error("缺少URL参数 --url")
        return
    
    logger.info(f"开始抓取网页: {args.url}")
    
    # 处理网页
    doc = await doc_manager.process_web_url(
        user_id=args.user_id,
        url=args.url,
        description="从网页抓取的内容"
    )
    
    logger.info(f"网页抓取成功: {doc.id}")
    logger.info(f"文档标题: {doc.title}")
    logger.info(f"文档类型: {doc.type}")
    logger.info(f"切片数量: {doc.chunks_count}")

async def list_documents():
    """列出文档测试"""
    logger.info(f"开始获取用户 {args.user_id} 的文档列表")
    
    docs = await doc_manager.get_documents(args.user_id)
    
    logger.info(f"找到 {len(docs)} 个文档:")
    for i, doc in enumerate(docs):
        logger.info(f"{i+1}. ID: {doc.id}")
        logger.info(f"   标题: {doc.title}")
        logger.info(f"   来源: {doc.source_type} - {doc.source}")
        logger.info(f"   类型: {doc.type}")
        logger.info(f"   切片: {doc.chunks_count}")
        logger.info(f"   创建时间: {doc.created_at}")
        logger.info("---")

async def search_documents():
    """搜索文档测试"""
    if not args.query:
        logger.error("缺少查询参数 --query")
        return
    
    # 如果指定了文档ID，搜索单个文档
    if args.doc_id:
        logger.info(f"开始在文档 {args.doc_id} 中搜索: {args.query}")
        chunks = await doc_manager.search_chunks(args.user_id, args.doc_id, args.query)
        
        logger.info(f"找到 {len(chunks)} 个匹配的切片:")
        for i, chunk in enumerate(chunks):
            logger.info(f"{i+1}. 切片ID: {chunk.id}")
            logger.info(f"   序号: {chunk.sequence}")
            logger.info(f"   内容: {chunk.content[:100]}...")
            logger.info("---")
    else:
        # 搜索所有文档
        logger.info(f"开始全局搜索: {args.query}")
        results = await doc_manager.search_documents(args.user_id, args.query)
        
        logger.info(f"找到 {len(results)} 个匹配的文档:")
        for i, (doc, chunks) in enumerate(results):
            logger.info(f"{i+1}. 文档ID: {doc.id}")
            logger.info(f"   标题: {doc.title}")
            logger.info(f"   匹配切片数: {len(chunks)}")
            
            # 显示前3个匹配的切片
            for j, chunk in enumerate(chunks[:3]):
                logger.info(f"   切片 {j+1}: {chunk.content[:100]}...")
            
            logger.info("---")

async def delete_document():
    """删除文档测试"""
    if not args.doc_id:
        logger.error("缺少文档ID参数 --doc_id")
        return
    
    logger.info(f"开始删除文档: {args.doc_id}")
    
    result = await doc_manager.delete_document(args.user_id, args.doc_id)
    
    if result:
        logger.info(f"文档删除成功: {args.doc_id}")
    else:
        logger.error(f"文档删除失败，可能不存在: {args.doc_id}")

async def main():
    """主函数"""
    await init_services()
    
    # 根据操作类型执行不同的测试
    if args.action == 'upload':
        await upload_file()
    elif args.action == 'web':
        await process_web()
    elif args.action == 'list':
        await list_documents()
    elif args.action == 'search':
        await search_documents()
    elif args.action == 'delete':
        await delete_document()
    
    # 关闭服务
    file_service.cancel_cleanup_task()

if __name__ == "__main__":
    asyncio.run(main()) 