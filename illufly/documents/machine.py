from statemachine import StateMachine, State
import time
import logging
from typing import Optional

class DocumentMachine(StateMachine):
    """文档处理状态机 - 增强版"""
    
    # 初始状态
    init = State('初始化', initial=True)
    
    # 来源状态（多种来源）
    uploaded = State('本地上传')
    bookmarked = State('网络收藏')
    saved_chat = State('对话收藏')
    
    # 从初始状态到各来源状态的转换
    set_uploaded = init.to(uploaded)
    set_bookmarked = init.to(bookmarked)
    set_saved_chat = init.to(saved_chat)
    
    # Markdown处理状态
    markdowning = State('Markdown转换中')
    markdowned = State('Markdown转换完成')
    markdown_failed = State('Markdown转换失败')
    
    # 切片状态
    chunking = State('切片中')
    chunked = State('切片完成')
    chunk_failed = State('切片失败')
    
    # QA处理状态（对话记录专用）
    qa_extracting = State('QA提取中')
    qa_extracted = State('QA提取完成')
    qa_extract_failed = State('QA提取失败')
    
    # 向量化状态
    embedding = State('向量化中')
    embedded = State('向量化完成')
    embedding_failed = State('向量化失败')
    
    # 状态转换定义 - 从不同来源开始处理
    # 1. 从上传文件到Markdown转换
    start_markdown_from_upload = uploaded.to(markdowning)
    # 2. 从网络收藏到Markdown转换
    start_markdown_from_bookmark = bookmarked.to(markdowning)
    
    # 3. 从对话记录提取QA
    start_qa_extraction = saved_chat.to(qa_extracting)
    complete_qa_extraction = qa_extracting.to(qa_extracted)
    fail_qa_extraction = qa_extracting.to(qa_extract_failed)
    retry_qa_from_failed = qa_extract_failed.to(qa_extracting)
    
    # Markdown处理
    complete_markdown = markdowning.to(markdowned)
    fail_markdown = markdowning.to(markdown_failed)
    retry_markdown_from_failed = markdown_failed.to(markdowning)
    
    # 切片处理 - 从Markdown开始
    start_chunking = markdowned.to(chunking)
    complete_chunking = chunking.to(chunked)
    fail_chunking = chunking.to(chunk_failed)
    retry_chunking_from_failed = chunk_failed.to(chunking)
    
    # 向量化处理 - 可以从切片或QA对开始
    start_embedding_from_chunks = chunked.to(embedding)
    start_embedding_from_qa = qa_extracted.to(embedding) # 关键修改：QA对可以直接向量化
    complete_embedding = embedding.to(embedded)
    fail_embedding = embedding.to(embedding_failed)
    retry_embedding_from_failed = embedding_failed.to(embedding)
    
    # 重新处理路径
    restart_markdown_from_embedded = embedded.to(markdowning)  # 重新处理Markdown
    restart_chunking_from_embedded = embedded.to(chunking)  # 重新处理切片
    restart_qa_extraction = embedded.to(qa_extracting)  # 重新提取QA对
    
    # 添加到状态机定义
    
    def __init__(self, document_service, user_id, document_id):
        self.service = document_service
        self.user_id = user_id
        self.document_id = document_id
        self.logger = document_service.logger or logging.getLogger(__name__)
        super().__init__()
    
    async def on_enter_markdowning(self):
        """开始Markdown转换"""
        self.logger.info(f"文档 {self.document_id} 进入Markdown转换中状态")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "markdowning",  # 更新状态
                "process_details": {
                    "markdowning": {
                        "started_at": time.time(),
                        "success": False
                    }
                }
            }
        )
    
    async def on_enter_markdowned(self):
        """Markdown转换完成"""
        self.logger.info(f"文档 {self.document_id} Markdown转换完成")
        now = time.time()
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "markdowned",  # 正确更新状态字段
                "process_details": {
                    "markdowning": {
                        "stage": "markdowned",
                        "finished_at": now,
                        "success": True
                    }
                },
                "has_markdown": True,
                "has_chunks": False,
                "has_embeddings": False
            }
        )
    
    async def on_enter_chunking(self):
        """开始切片"""
        self.logger.info(f"文档 {self.document_id} 进入切片中状态")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "chunking",  # 更新顶级状态字段
                "process_details": {
                    "chunking": {
                        "stage": "chunking",
                        "started_at": time.time(),
                        "success": False
                    }
                }
            }
        )
    
    async def on_enter_chunked(self, chunks_count=0, avg_length=0):
        """切片完成"""
        self.logger.info(f"文档 {self.document_id} 切片完成，共{chunks_count}个切片")
        now = time.time()
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "chunked",  # 正确更新状态字段
                "process_details": {
                    "chunking": {
                        "stage": "chunked",
                        "finished_at": now,
                        "success": True,
                        "details": {
                            "chunks_count": chunks_count,
                            "avg_chunk_length": avg_length
                        }
                    }
                },
                "has_chunks": True
            }
        )
    
    async def on_enter_embedding(self):
        """开始向量化"""
        self.logger.info(f"文档 {self.document_id} 进入向量化中状态")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "embedding",  # 更新顶级状态字段
                "process_details": {
                    "embedding": {
                        "stage": "embedding",
                        "started_at": time.time(),
                        "success": False
                    }
                }
            }
        )
    
    async def on_enter_embedded(self, indexed_chunks=0):
        """向量化完成"""
        self.logger.info(f"文档 {self.document_id} 向量化完成，索引了{indexed_chunks}个切片")
        now = time.time()
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "embedded",  # 正确更新状态字段
                "process_details": {
                    "embedding": {
                        "stage": "embedded",
                        "finished_at": now,
                        "success": True,
                        "details": {
                            "indexed_chunks": indexed_chunks
                        }
                    }
                },
                "has_embeddings": True
            }
        )
    
    async def on_enter_failed(self, source, error=None):
        """进入失败状态"""
        phase = source.id  # 获取源状态名称
        self.logger.error(f"文档 {self.document_id} 处理失败: {phase}, 错误: {error}")
        
        stage_map = {
            "markdowning": "markdowning",
            "chunking": "chunking",
            "embedding": "embedding"
        }
        
        phase_name = stage_map.get(phase)
        if not phase_name:
            return
            
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "failed",  # 更新顶级状态字段
                "process_details": {
                    phase_name: {
                        "stage": "failed",
                        "error": str(error) if error else "未知错误",
                        "finished_at": time.time(),
                        "success": False
                    }
                }
            }
        )

    def is_processing_state(self, state: str) -> bool:
        """判断是否为处理中状态"""
        return state in ["markdowning", "chunking", "embedding"]

    def is_completed_state(self, state: str) -> bool:
        """判断是否为完成状态"""
        return state in ["markdowned", "chunked", "embedded"]

    def get_next_state(self, current_state: str) -> Optional[str]:
        """获取下一个状态"""
        # 根据来源和当前状态确定下一步
        source_to_sequence = {
            "uploaded": ["uploaded", "markdowned", "chunked", "embedded"],
            "bookmarked": ["bookmarked", "markdowned", "chunked", "embedded"],
            "saved_chat": ["saved_chat", "qa_extracted", "embedded"]
        }
        
        # 确定文档来源
        for source, sequence in source_to_sequence.items():
            if current_state in sequence:
                idx = sequence.index(current_state)
                if idx < len(sequence) - 1:
                    return sequence[idx + 1]
        
        return None

    # 辅助判断方法
    def has_markdown(self) -> bool:
        """判断当前状态是否已有Markdown"""
        completed_states = ["markdowned", "chunking", "chunked", "embedding", "embedded"]
        return self.current_state.id in completed_states
    
    def has_chunks(self) -> bool:
        """判断当前状态是否已有切片"""
        completed_states = ["chunked", "embedding", "embedded"]
        return self.current_state.id in completed_states
    
    def has_qa_pairs(self) -> bool:
        """判断当前状态是否已有QA对"""
        completed_states = ["qa_extracted", "embedding", "embedded"]
        return self.current_state.id in completed_states
    
    def has_embeddings(self) -> bool:
        """判断当前状态是否已有向量索引"""
        return self.current_state.id == "embedded"
    
    def get_source_type(self) -> str:
        """获取文档来源类型"""
        if self.current_state.id in ["uploaded", "markdowning", "markdowned", "markdown_failed"]:
            return "local"
        elif self.current_state.id in ["bookmarked"]:
            return "web"
        elif self.current_state.id in ["saved_chat", "qa_extracting", "qa_extracted", "qa_extract_failed"]:
            return "chat"
        else:
            # 对于中间状态，需要查询元数据获取来源
            return "unknown"
    
    def is_processing(self) -> bool:
        """判断是否正在处理中"""
        processing_states = ["markdowning", "chunking", "embedding", "qa_extracting"]
        return self.current_state.id in processing_states
    
    def has_failed(self) -> bool:
        """判断是否有任何阶段失败"""
        failed_states = ["markdown_failed", "chunk_failed", "embedding_failed", "qa_extract_failed"]
        return self.current_state.id in failed_states
    
    def get_failed_stage(self) -> Optional[str]:
        """获取失败的阶段"""
        if self.current_state.id == "markdown_failed":
            return "markdown"
        elif self.current_state.id == "chunk_failed":
            return "chunking"
        elif self.current_state.id == "embedding_failed":
            return "embedding"
        elif self.current_state.id == "qa_extract_failed":
            return "qa_extraction"
        return None

    async def activate_with_source(self, source_type: str):
        """根据文档来源激活对应的初始状态"""
        if self.current_state.id != 'init':
            return  # 已经设置了状态
            
        if source_type == "local":
            await self.set_uploaded()
        elif source_type == "web":
            await self.set_bookmarked()
        elif source_type == "chat":
            await self.set_saved_chat()

    async def on_enter_qa_extracting(self):
        """开始QA提取"""
        self.logger.info(f"文档 {self.document_id} 开始QA提取")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "qa_extracting",
                "process_details": {
                    "qa_extraction": {
                        "stage": "qa_extracting",
                        "started_at": time.time(),
                        "success": False
                    }
                }
            }
        )

    async def on_enter_markdown_failed(self, error=None):
        """进入Markdown转换失败状态"""
        self.logger.error(f"文档 {self.document_id} Markdown转换失败: {error}")
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "markdown_failed",  # 更新为特定失败状态
                "process_details": {
                    "markdown": {
                        "stage": "failed",
                        "error": str(error) if error else "未知错误",
                        "finished_at": time.time(),
                        "success": False
                    }
                }
            }
        )

    async def on_enter_qa_extracted(self, qa_pairs_count=0):
        """QA提取完成"""
        self.logger.info(f"文档 {self.document_id} QA提取完成，共{qa_pairs_count}个问答对")
        now = time.time()
        await self.service.update_metadata(
            self.user_id, self.document_id,
            {
                "state": "qa_extracted",
                "process_details": {
                    "qa_extraction": {
                        "stage": "completed",
                        "finished_at": now,
                        "success": True,
                        "details": {
                            "qa_pairs_count": qa_pairs_count
                        }
                    }
                },
                "has_qa_pairs": True
            }
        )
