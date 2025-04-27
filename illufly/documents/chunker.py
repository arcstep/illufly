from typing import List, Dict, Any, Optional
import logging
import re
import tiktoken

logger = logging.getLogger(__name__)

class Chunker:
    """文档切片器基类"""
    
    def __init__(self, max_chunk_size: int = 1000, overlap: int = 100):
        """初始化切片器
        
        Args:
            max_chunk_size: 每个切片的最大 token 数 (通过子类实现)
            overlap: 相邻切片之间的重叠 token 数 (通过子类实现)
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
    
    async def chunk_document(self, content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """将文档内容切分为多个切片"""
        raise NotImplementedError("子类必须实现此方法")

class MarkdownChunker(Chunker):
    """基于Markdown结构的文档切片器 - 使用tiktoken进行切分"""

    def __init__(self, max_chunk_size: int = 1000, overlap: int = 100, model_name: str = "gpt-3.5-turbo"):
        """初始化切片器

        Args:
            max_chunk_size: 每个切片的最大 token 数
            overlap: 相邻切片之间的重叠 token 数
            model_name: 用于 tiktoken 编码的模型名称
        """
        super().__init__(max_chunk_size, overlap)
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(f"模型 '{model_name}' 的 tiktoken 编码器未找到，将使用 'cl100k_base'")
            self.encoding = tiktoken.get_encoding("cl100k_base")

    async def chunk_document(self, content: str, metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """将Markdown内容切分为多个有意义的切片 (基于Token)"""
        content = content.strip() # Start with stripped content
        if not content:
            return []

        final_chunks_data = [] # Store {"content": ..., "title": ...} temporarily

        # 查找所有标题及其位置和级别
        headers = []
        # Find lines starting with #, ##, ..., ###### followed by a space
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', content, re.MULTILINE):
            headers.append({
                'start': match.start(),
                'title': match.group(2).strip()
            })

        last_pos = 0
        current_section_title = "文档开头" # Default title

        # --- 修改后的逻辑 ---
        # 1. 如果没有标题，直接处理整个文档
        if not headers:
            logger.debug("Processing content with no headers")
            self._add_section_chunks(final_chunks_data, content, current_section_title)
        else:
            # 2. 处理第一个标题之前的内容（如果有）
            first_header_start = headers[0]['start']
            if first_header_start > 0:
                initial_content = content[last_pos:first_header_start].strip()
                if initial_content:
                    logger.debug(f"Processing content before first header (title: '{current_section_title}')")
                    self._add_section_chunks(final_chunks_data, initial_content, current_section_title)
            # 设置 last_pos 为第一个标题的开始，准备迭代
            last_pos = first_header_start

            # 3. 迭代处理每个标题定义的部分
            for i, header in enumerate(headers):
                current_section_title = header['title']
                start_pos = header['start'] # 当前标题的开始位置 (即 last_pos)
                # 结束位置是下一个标题的开始，或文档末尾
                end_pos = headers[i+1]['start'] if i + 1 < len(headers) else len(content)

                # 提取当前标题定义的整个部分内容（包含标题行）
                section_content = content[start_pos:end_pos].strip()

                if section_content:
                    logger.debug(f"Processing section starting with header '{current_section_title}'")
                    # 对这部分内容进行切片（可能切成多块），使用当前标题
                    self._add_section_chunks(final_chunks_data, section_content, current_section_title)
                # 更新 last_pos，为下一次迭代或结束做准备（虽然在此循环中不再需要）
                last_pos = end_pos
        # --- 结束修改后的逻辑 ---


        # 4. 后处理：添加最终元数据并清理
        processed_chunks = []
        # Get count *before* filtering potentially empty ones if any slip through
        final_len = len(final_chunks_data)
        for i, chunk_data in enumerate(final_chunks_data):
            # Filter empty just in case
            if not chunk_data.get("content", "").strip():
                continue

            chunk_metadata = metadata.copy() if metadata else {}
            chunk_metadata.update({
                "index": i, # Use index from this loop iteration
                "total_chunks": final_len, # Use pre-filter count for total initially
                "next_index": i + 1 if i < final_len - 1 else None, # Link based on this loop's index
                "prev_index": i - 1 if i > 0 else None, # Link based on this loop's index
                "chunk_title": chunk_data.get("title", "未知标题") # Get title associated during _add_section_chunks
            })
            # Final chunk structure
            processed_chunks.append({
                "content": chunk_data["content"],
                "metadata": chunk_metadata
            })

        # Recalculate indices based on the actual final list length if filtering happened
        final_processed_len = len(processed_chunks)
        if final_processed_len != final_len: # Check if filtering removed any items
            logger.warning(f"Chunk filtering removed {final_len - final_processed_len} items. Recalculating indices.")
            for i, chunk in enumerate(processed_chunks):
                chunk["metadata"]["index"] = i
                chunk["metadata"]["total_chunks"] = final_processed_len
                chunk["metadata"]["next_index"] = i + 1 if i < final_processed_len - 1 else None
                chunk["metadata"]["prev_index"] = i - 1 if i > 0 else None

        return processed_chunks

    def _token_len(self, text: str) -> int:
        """使用 tiktoken 计算 token 数"""
        # Note: encoding can be slow for very large texts, consider chunking encoding if performance issue arises
        return len(self.encoding.encode(text))

    def _add_section_chunks(self,
        chunks_list: List[Dict[str, Any]],
        content: str,
        title: str
    ):
        """将一段内容按 token 数切分，保留段落边界并添加 overlap"""
        content = content.strip()
        if not content:
            logger.debug("--> _add_section_chunks received empty content, skipping.")
            return

        total_tokens = self._token_len(content)
        logger.debug(f"--> _add_section_chunks processing section titled '{title}', total tokens: {total_tokens}, max_chunk_size: {self.max_chunk_size}")
        
        # 强制分块阈值 
        force_split_threshold = int(self.max_chunk_size * 0.7)  # 调低阈值以更积极地分块

        # 提取标题行
        header_line = ""
        header_match = re.match(r'^(#{1,6}\s+.+?)(?:\n|$)', content)
        if header_match:
            header_line = header_match.group(1)
            header_tokens = self._token_len(header_line)
        else:
            header_tokens = 0
        
        # Check if content is ONLY a title line
        is_only_title = bool(re.match(r'^(#{1,6}\s+[^\n]+)\s*$', content))
        logger.debug(f"--> _add_section_chunks: Is content only a title line? {is_only_title}")

        # If total tokens within limit AND it's not just a title line, add as one chunk
        if total_tokens <= force_split_threshold and not is_only_title:
            logger.debug(f"--> _add_section_chunks: Adding as single chunk (within limit, not just title). Content starts: '{content[:50]}...'")
            chunks_list.append({"content": content, "title": title})
            return
        # If it's only a title line, skip entirely
        elif is_only_title:
            logger.debug("--> _add_section_chunks: Skipping as content is only a title line.")
            return

        # --- Content exceeds limit OR is not just a title - proceed with paragraph splitting ---
        logger.debug(f"--> _add_section_chunks: Content exceeds limit or has substance beyond title. Splitting by paragraph. Content starts: '{content[:50]}...'")
        
        # 无标题内容特殊处理
        if not header_line:
            self._split_no_header_content(chunks_list, content, title)
            return
        
        # 有标题内容的处理
        paragraphs = re.split(r'\n\s*\n', content)
        current_chunk = ""
        current_tokens = 0
        
        # 处理标题行
        if paragraphs and paragraphs[0].strip().startswith('#'):
            header_para = paragraphs[0].strip()
            current_chunk = header_para
            current_tokens = self._token_len(current_chunk)
            paragraphs = paragraphs[1:]  # 移除标题
        
        # 保留原始段落以便识别超大段落
        original_paragraphs = [p.strip() for p in paragraphs if p.strip()]
        large_paragraphs = [p for p in original_paragraphs if self._token_len(p) > (self.max_chunk_size - header_tokens)]
        
        # 预先计算每个段落的token
        para_tokens_map = {p: self._token_len(p) for p in original_paragraphs}
        
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            
            para_tokens = para_tokens_map.get(para, self._token_len(para))
            separator_tokens = self._token_len("\n\n") if current_chunk else 0
            
            # 检查是否是超大段落
            is_large_para = para in large_paragraphs
            
            # 计算有效限制 - 为标题预留空间
            effective_limit = self.max_chunk_size - header_tokens
            
            # 如果段落会导致超过限制，创建新块
            if current_chunk and (current_tokens + para_tokens + separator_tokens > effective_limit):
                # 保存当前块
                chunks_list.append({"content": current_chunk, "title": title})
                
                # 如果当前段落自身超出限制，单独处理
                if is_large_para:
                    logger.warning(f"Paragraph too large ({para_tokens} > {effective_limit}), adding as separate chunk.")
                    # 确保不超过max_chunk_size，必要时截断
                    if header_tokens + para_tokens > self.max_chunk_size:
                        # 尝试将段落分成更小的部分
                        if para_tokens > 50:  # 只在段落足够大时尝试分割
                            # 按句子分割
                            sentences = re.split(r'([.!?]\s+)', para)
                            # 合并句子和标点符号
                            actual_sentences = []
                            current_sentence = ""
                            for s in sentences:
                                if re.match(r'[.!?]\s+', s):
                                    current_sentence += s
                                    actual_sentences.append(current_sentence)
                                    current_sentence = ""
                                else:
                                    current_sentence = s
                            if current_sentence:
                                actual_sentences.append(current_sentence)
                                
                            if len(actual_sentences) > 1:  # 确保有多个句子
                                current_chunk = header_line
                                current_tokens = header_tokens
                                
                                for sentence in actual_sentences:
                                    sentence_tokens = self._token_len(sentence)
                                    if current_tokens + sentence_tokens + separator_tokens > self.max_chunk_size:
                                        # 保存当前块并开始新块
                                        chunks_list.append({"content": current_chunk, "title": title})
                                        current_chunk = header_line + "\n\n" + sentence
                                        current_tokens = header_tokens + 2 + sentence_tokens
                                    else:
                                        # 添加到当前块
                                        if current_chunk == header_line:
                                            current_chunk += "\n\n" + sentence
                                            current_tokens += 2 + sentence_tokens
                                        else:
                                            current_chunk += " " + sentence  # 不增加段落间隔
                                            current_tokens += 1 + sentence_tokens
                                
                                continue  # 跳过下面的处理，因为已经处理完这个段落
                    
                    # 如果无法按句子分割，则整体添加，但确保不超过max_chunk_size
                    safe_para = para
                    if header_tokens + para_tokens > self.max_chunk_size:
                        # 计算可用token数
                        available_tokens = self.max_chunk_size - header_tokens - 5  # 为省略号留空间
                        if available_tokens > 0:
                            # 按token截断段落
                            token_ids = self.encoding.encode(para)
                            if len(token_ids) > available_tokens:
                                safe_para = self.encoding.decode(token_ids[:available_tokens]) + "..."
                    
                    chunks_list.append({"content": f"{header_line}\n\n{safe_para}", "title": title})
                    current_chunk = ""
                    current_tokens = 0
                    continue
                
                # 非超大段落的重叠处理
                content_without_header = current_chunk
                if content_without_header.startswith(header_line):
                    content_without_header = re.sub(r'^' + re.escape(header_line) + r'\s*\n\n', '', content_without_header, 1)
                
                token_ids = self.encoding.encode(content_without_header)
                overlap_ids = token_ids[-min(self.overlap, len(token_ids)):] 
                
                try:
                    overlap_text = self.encoding.decode(overlap_ids).strip()
                except Exception as e:
                    logger.warning(f"Tiktoken decode error: {e}")
                    overlap_text = ""
                    
                # 精确计算块大小，确保不超过限制
                if overlap_text:
                    # 计算标题+重叠+段落的总大小
                    combined_content = f"{header_line}\n\n{overlap_text}\n\n{para}"
                    combined_tokens = self._token_len(combined_content)
                    
                    # 如果超过限制，尝试减少重叠
                    if combined_tokens > self.max_chunk_size:
                        # 尝试只使用重叠的一半
                        half_overlap = overlap_text[:len(overlap_text)//2].strip()
                        if half_overlap:
                            half_combined = f"{header_line}\n\n{half_overlap}\n\n{para}"
                            half_tokens = self._token_len(half_combined)
                            if half_tokens <= self.max_chunk_size:
                                current_chunk = half_combined
                                current_tokens = half_tokens
                            else:
                                # 如果仍然超过，只使用标题和段落
                                current_chunk = f"{header_line}\n\n{para}"
                                current_tokens = self._token_len(current_chunk)
                        else:
                            # 如果无法减半，只使用标题和段落
                            current_chunk = f"{header_line}\n\n{para}"
                            current_tokens = self._token_len(current_chunk)
                    else:
                        current_chunk = combined_content
                        current_tokens = combined_tokens
                else:
                    # 没有重叠，只使用标题和段落
                    current_chunk = f"{header_line}\n\n{para}"
                    current_tokens = self._token_len(current_chunk)
                    
                # 最终安全检查 - 确保不超过限制
                if current_tokens > self.max_chunk_size:
                    logger.warning(f"Even after optimization, chunk tokens ({current_tokens}) > max_chunk_size ({self.max_chunk_size}). Truncating.")
                    # 紧急截断
                    token_ids = self.encoding.encode(current_chunk)
                    if len(token_ids) > self.max_chunk_size:
                        current_chunk = self.encoding.decode(token_ids[:self.max_chunk_size-3]) + "..."
                        current_tokens = self._token_len(current_chunk)
            else:
                # 可以添加到当前块
                if current_chunk:
                    current_chunk += f"\n\n{para}"
                    current_tokens += para_tokens + separator_tokens
                else:
                    current_chunk = para
                    current_tokens = para_tokens
        
        # 添加最后一个块
        if current_chunk:
            # 最终安全检查
            if current_tokens > self.max_chunk_size:
                logger.warning(f"Final chunk exceeds limit ({current_tokens} > {self.max_chunk_size}). Truncating.")
                token_ids = self.encoding.encode(current_chunk)
                if len(token_ids) > self.max_chunk_size:
                    current_chunk = self.encoding.decode(token_ids[:self.max_chunk_size-3]) + "..."
            
            chunks_list.append({"content": current_chunk, "title": title})

    def _split_no_header_content(self, chunks_list, content, title):
        """专门处理无标题内容的分块"""
        paragraphs = re.split(r'\n\s*\n', content) 
        current_chunk = ""
        current_tokens = 0
        
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if not para:
                continue
            
            para_tokens = self._token_len(para)
            separator_tokens = self._token_len("\n\n") if current_chunk else 0
            
            # 检查段落自身是否超过限制
            if para_tokens > self.max_chunk_size:
                # 如果当前块非空，先保存
                if current_chunk:
                    chunks_list.append({"content": current_chunk, "title": title})
                    current_chunk = ""
                    current_tokens = 0
                
                # 添加超大段落
                logger.warning(f"--> _split_no_header_content: Paragraph {i} exceeds limit ({para_tokens} > {self.max_chunk_size}). Adding as is.")
                chunks_list.append({"content": para, "title": title})
                continue
            
            # 如果添加段落会超过限制，保存当前块并开始新块
            if current_chunk and current_tokens + para_tokens + separator_tokens > self.max_chunk_size:
                # 保存当前块
                chunks_list.append({"content": current_chunk, "title": title})
                
                # 计算重叠部分
                token_ids = self.encoding.encode(current_chunk)
                overlap_ids = token_ids[-self.overlap:] if len(token_ids) >= self.overlap else token_ids
                try:
                    overlap_text = self.encoding.decode(overlap_ids).strip()
                except Exception as e:
                    logger.warning(f"Tiktoken decode error: {e}")
                    overlap_text = ""
                    
                # 新块以重叠部分开始（如果有）
                if overlap_text:
                    current_chunk = f"{overlap_text}\n\n{para}"
                else:
                    current_chunk = para
                    
                current_tokens = self._token_len(current_chunk)
            # 可以添加到当前块
            else:
                if current_chunk:
                    current_chunk += f"\n\n{para}"
                    current_tokens += para_tokens + separator_tokens
                else:
                    current_chunk = para
                    current_tokens = para_tokens
        
        # 添加最后一个块
        if current_chunk:
            chunks_list.append({"content": current_chunk, "title": title})


# 工厂函数，根据文档类型选择合适的切片器
def get_chunker(doc_type: str = "markdown", **kwargs) -> Chunker:
    """获取适合特定文档类型的切片器
    
    Args:
        doc_type: 文档类型，如 "markdown", "text" 等
        **kwargs: 传递给切片器的参数
        
    Returns:
        Chunker: 切片器实例
    """
    if doc_type.lower() in ["markdown", "md"]:
        return MarkdownChunker(**kwargs)
    else:
        # 默认使用Markdown切片器
        logger.warning(f"未知的文档类型: {doc_type}，使用默认Markdown切片器")
        return MarkdownChunker(**kwargs)
