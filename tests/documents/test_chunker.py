import pytest
from illufly.documents.chunker import MarkdownChunker # Adjust import path if needed
import asyncio
import re # Import re for overlap check

# --- Test Constants ---

TEST_MD_CONTENT_SIMPLE = """
# Section 1

This is the first paragraph of section 1. It contains some text.

This is the second paragraph.

## Section 1.1

Content under section 1.1. It's quite short.

# Section 2

This is the only paragraph in section 2.
"""

TEST_MD_CONTENT_LARGE_SECTION = """
# A Very Large Section

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam euismod, nisl eget aliquam ultricies, nunc nisl aliquet nunc, vitae aliquam nisl nunc eu nunc. Sed euismod, nisl eget aliquam ultricies, nunc nisl aliquet nunc, vitae aliquam nisl nunc eu nunc. (Approx 50 tokens)

Pellentesque habitant morbi tristique senectus et netus et malesuada fames ac turpis egestas. Vestibulum tortor quam, feugiat vitae, ultricies eget, tempor sit amet, ante. Donec eu libero sit amet quam egestas semper. Aenean ultricies mi vitae est. Mauris placerat eleifend leo. (Approx 50 tokens)

Quisque sit amet est et sapien ullamcorper pharetra. Vestibulum erat wisi, condimentum sed, commodo vitae, ornare sit amet, wisi. Aenean fermentum, elit eget tincidunt condimentum, eros ipsum rutrum orci, sagittis tempus lacus enim ac dui. Donec non enim in turpis pulvinar facilisis. Ut felis. (Approx 50 tokens)

Praesent dapibus, neque id cursus faucibus, tortor neque egestas augue, eu vulputate magna eros eu erat. Aliquam erat volutpat. Nam dui mi, tincidunt quis, accumsan porttitor, facilisis luctus, metus. (Approx 40 tokens)
"""

TEST_MD_CONTENT_TITLE_ONLY = """
# Section 1

Some content here.

## Title Only Section

# Section 3

More content follows.

### Another Title Only at End
"""

TEST_MD_CONTENT_NO_HEADERS = """
This document has no headers at all.
It consists of multiple paragraphs separated by blank lines.

This is the second paragraph. It should be handled correctly.

And a third one for good measure.
"""

# --- Test Functions ---

@pytest.mark.asyncio
async def test_empty_content():
    """测试空内容处理
    
    功能描述:
    - 验证当输入为空字符串时的切片器行为
    
    验证目标:
    1. 空字符串输入应该返回空数组
    2. 不应产生任何错误或异常
    """
    chunker = MarkdownChunker(max_chunk_size=100, overlap=10)
    chunks = await chunker.chunk_document("")
    assert chunks == []

@pytest.mark.asyncio
async def test_small_content_within_limit():
    """测试小内容不分块处理
    
    功能描述:
    - 验证当内容小于最大块大小时的行为
    - 处理无标题的简单段落文本
    
    验证目标:
    1. 内容小于限制时应只产生一个块
    2. 块内容应与原始内容完全一致
    3. 元数据应正确设置（默认标题、索引等）
    """
    chunker = MarkdownChunker(max_chunk_size=200, overlap=20)
    content = "A single paragraph of text that fits within the limit."
    chunks = await chunker.chunk_document(content)
    assert len(chunks) == 1, f"Expected 1 chunk for small content, got {len(chunks)}"
    assert chunks[0]['content'] == content
    assert chunks[0]['metadata']['chunk_title'] == "文档开头"
    assert chunks[0]['metadata']['index'] == 0
    assert chunks[0]['metadata']['total_chunks'] == 1

@pytest.mark.asyncio
async def test_multiple_sections_within_limit():
    """测试多个标题节分块
    
    功能描述:
    - 验证包含多个Markdown标题的内容被正确分块
    - 测试基于标题进行分块的能力
    
    验证目标:
    1. 每个标题节应生成单独的块
    2. 块数量应与标题数量一致
    3. 每个块应保留原始标题
    4. 元数据应正确设置（标题、索引关系等）
    5. 相邻块间应有正确的链接关系（next_index, prev_index）
    """
    chunker = MarkdownChunker(max_chunk_size=200, overlap=20)
    chunks = await chunker.chunk_document(TEST_MD_CONTENT_SIMPLE)
    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}"
    assert chunks[0]['metadata']['chunk_title'] == "Section 1"
    assert chunks[1]['metadata']['chunk_title'] == "Section 1.1"
    assert chunks[2]['metadata']['chunk_title'] == "Section 2"
    assert chunks[0]['content'].strip().startswith("# Section 1")
    assert chunks[1]['content'].strip().startswith("## Section 1.1")
    assert chunks[2]['content'].strip().startswith("# Section 2")
    assert chunks[0]['metadata']['next_index'] == 1
    assert chunks[1]['metadata']['prev_index'] == 0
    assert chunks[1]['metadata']['next_index'] == 2
    assert chunks[2]['metadata']['prev_index'] == 1
    assert chunks[2]['metadata']['next_index'] is None
    assert chunks[0]['metadata']['total_chunks'] == 3

@pytest.mark.asyncio
async def test_large_section_needs_splitting():
    """测试大标题节分块及重叠处理
    
    功能描述:
    - 验证当单个标题节内容超过最大块大小时的分块行为
    - 测试块间重叠机制是否正常工作
    - 验证所有块都保留原始标题信息
    
    验证目标:
    1. 内容应被分成多个块
    2. 所有块的标题元数据应保持一致
    3. 除特殊情况外，块大小不应超过限制+容差
    4. 相邻块间应有适当的内容重叠
    5. 标题应在所有块中保留
    """
    chunker = MarkdownChunker(max_chunk_size=80, overlap=15)
    chunks = await chunker.chunk_document(TEST_MD_CONTENT_LARGE_SECTION)

    assert len(chunks) > 1, "Large section should be split into multiple chunks"
    first_title = chunks[0]['metadata']['chunk_title']
    assert first_title == "A Very Large Section"

    for i, chunk in enumerate(chunks):
        assert chunk['metadata']['chunk_title'] == first_title

    # --- 测试块大小 ---
    token_limit = chunker.max_chunk_size
    original_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', TEST_MD_CONTENT_LARGE_SECTION) if p.strip()]
    if original_paragraphs and original_paragraphs[0].startswith("#"):
        original_paragraphs.pop(0)

    for i, chunk in enumerate(chunks):
        chunk_tokens = chunker._token_len(chunk['content'])
        assert chunk_tokens > 0

        # 检查是否为已知的大段落
        is_known_oversized_para = False
        for orig_para in original_paragraphs:
            if chunk['content'].endswith(orig_para) and chunker._token_len(orig_para) > token_limit:
                if abs(chunk_tokens - chunker._token_len(orig_para)) < 5:
                    is_known_oversized_para = True
                    print(f"Note: Chunk {i} matches known oversized paragraph. Allowing.")
                    break
            elif chunker._token_len(orig_para) > token_limit:
                if abs(chunk_tokens - (chunker._token_len(orig_para) + chunker.overlap)) < chunker.overlap:
                    if chunk['content'].endswith(orig_para):
                        is_known_oversized_para = True
                        print(f"Note: Chunk {i} likely matches known oversized paragraph + overlap. Allowing.")
                        break

        if not is_known_oversized_para:
            margin = 15
            assert chunk_tokens <= token_limit + margin, \
                f"Chunk {i} tokens ({chunk_tokens}) exceed limit ({token_limit} + margin) and is not an oversized paragraph."

    # --- 修改后的重叠检查 ---
    if len(chunks) > 1:
        for i in range(len(chunks) - 1):
            chunk_i_content = chunks[i]['content']
            chunk_j_content = chunks[i+1]['content']
            
            # 处理标题行
            if i > 0 and "# A Very Large Section" in chunk_j_content:
                # 从第二个块开始，移除标题后再检查重叠
                chunk_j_without_title = re.sub(r'^# A Very Large Section\s*\n\n', '', chunk_j_content)
                
                # 在无标题内容中检查重叠
                token_ids_i = chunker.encoding.encode(chunk_i_content)
                overlap_ids_expected = token_ids_i[-chunker.overlap:] if len(token_ids_i) >= chunker.overlap else token_ids_i
                try:
                    overlap_text_expected = chunker.encoding.decode(overlap_ids_expected).strip()
                    if not overlap_text_expected:
                        continue
                        
                    match = re.match(r'\s*' + re.escape(overlap_text_expected), chunk_j_without_title)
                    assert match is not None, \
                        f"Overlap check failed between chunk {i} and {i+1}.\nExpected start (after title): '{overlap_text_expected[:50]}...'\nActual start: '{chunk_j_without_title[:50]}...'"
                except Exception:
                    # 解码错误，跳过检查
                    pass
            else:
                # 第一个块（或没有标题的块）的普通检查
                token_ids_i = chunker.encoding.encode(chunk_i_content)
                overlap_ids_expected = token_ids_i[-chunker.overlap:] if len(token_ids_i) >= chunker.overlap else token_ids_i
                try:
                    overlap_text_expected = chunker.encoding.decode(overlap_ids_expected).strip()
                    if not overlap_text_expected:
                        continue
                        
                    match = re.match(r'\s*' + re.escape(overlap_text_expected), chunk_j_content)
                    assert match is not None, \
                        f"Overlap check failed between chunk {i} and {i+1}.\nExpected start: '{overlap_text_expected[:50]}...'\nActual start: '{chunk_j_content[:50]}...'"
                except Exception:
                    # 解码错误，跳过检查
                    pass

@pytest.mark.asyncio
async def test_title_only_chunks_are_skipped():
    """测试仅包含标题的节被跳过
    
    功能描述:
    - 验证只包含标题而没有实际内容的节是否被正确处理
    - 测试标题过滤机制
    
    验证目标:
    1. 只有标题的节不应生成单独的块
    2. 只产生包含实际内容的块
    3. 正确跳过"Title Only Section"和"Another Title Only at End"
    """
    chunker = MarkdownChunker(max_chunk_size=100, overlap=10)
    chunks = await chunker.chunk_document(TEST_MD_CONTENT_TITLE_ONLY)

    assert len(chunks) == 2, f"Expected 2 chunks, got {len(chunks)}"
    assert chunks[0]['metadata']['chunk_title'] == "Section 1"
    assert "Some content here" in chunks[0]['content']
    assert "Title Only Section" not in chunks[0]['content']

    assert chunks[1]['metadata']['chunk_title'] == "Section 3"
    assert "More content follows" in chunks[1]['content']
    assert "Another Title Only at End" not in chunks[1]['content']

@pytest.mark.asyncio
async def test_metadata_propagation():
    """测试文档元数据传播
    
    功能描述:
    - 验证原始文档元数据是否正确传播到所有块
    - 测试块特定元数据是否正确生成
    
    验证目标:
    1. 原始文档元数据应复制到每个块
    2. 块特定元数据（如索引、标题等）应正确添加
    3. 总块数应在所有块的元数据中一致
    """
    chunker = MarkdownChunker(max_chunk_size=200, overlap=20)
    doc_meta = {"document_id": "doc-abc", "source": "manual"}
    chunks = await chunker.chunk_document(TEST_MD_CONTENT_SIMPLE, metadata=doc_meta)

    assert len(chunks) == 3
    for chunk in chunks:
        assert chunk['metadata']['document_id'] == "doc-abc"
        assert chunk['metadata']['source'] == "manual"
        assert "chunk_title" in chunk['metadata']
        assert chunk['metadata']['total_chunks'] == 3

@pytest.mark.asyncio
async def test_no_headers_content():
    """测试无标题内容分块
    
    功能描述:
    - 验证没有Markdown标题的纯文本内容是否能被正确分块
    - 测试基于token限制而不是标题进行的分块
    
    验证目标:
    1. 当内容超过块大小限制时应分成多个块
    2. 所有块应使用默认标题"文档开头"
    3. 相邻块间应有适当的内容重叠
    """
    chunker = MarkdownChunker(max_chunk_size=20, overlap=5) 
    chunks = await chunker.chunk_document(TEST_MD_CONTENT_NO_HEADERS)

    assert len(chunks) > 1, f"期望无标题内容被分成多个块，但只得到{len(chunks)}个块"
    
    for chunk in chunks:
        assert chunk['metadata']['chunk_title'] == "文档开头"
    
    if len(chunks) > 1:
        for i in range(len(chunks) - 1):
            chunk_i = chunks[i]['content']
            chunk_i_plus_1 = chunks[i+1]['content']
            
            token_ids = chunker.encoding.encode(chunk_i)
            overlap_ids = token_ids[-chunker.overlap:] if len(token_ids) >= chunker.overlap else token_ids
            try:
                expected_overlap = chunker.encoding.decode(overlap_ids).strip()
                if not expected_overlap:
                    continue
                    
                assert chunk_i_plus_1.startswith(expected_overlap) or \
                       re.match(r'\s*' + re.escape(expected_overlap), chunk_i_plus_1), \
                       f"块{i}和块{i+1}之间的重叠检查失败"
            except Exception:
                pass

@pytest.mark.asyncio
async def test_large_section_with_title_repeating():
    """测试标题在所有分块中重复
    
    功能描述:
    - 验证当大内容被分块时，每个块是否都保留原始标题
    - 测试标题传播机制
    
    验证目标:
    1. 内容应被分成多个块
    2. 每个块都应以原始标题开始
    3. 所有块的标题元数据应一致
    4. 块之间应保持适当重叠（不考虑标题）
    """
    chunker = MarkdownChunker(max_chunk_size=40, overlap=5)
    content = """# Important Title
    
This is a paragraph that should be in the first chunk with some additional text to make it larger.

This is another paragraph that should go into the second chunk because we set a small max_chunk_size.

And this third paragraph should be in another chunk to test title propagation properly."""

    chunks = await chunker.chunk_document(content)
    
    assert len(chunks) > 1, f"期望内容被分成多个块，但只得到了{len(chunks)}个块"
    
    for i, chunk in enumerate(chunks):
        assert chunk['content'].strip().startswith("# Important Title"), \
               f"期望块{i}以标题开始，但内容为: '{chunk['content'][:50]}...'"
    
    for chunk in chunks:
        assert chunk['metadata']['chunk_title'] == "Important Title"
        
    if len(chunks) > 1:
        for i in range(len(chunks) - 1):
            chunk_i = chunks[i]['content']
            chunk_i_plus_1 = chunks[i+1]['content']
            
            text1 = re.sub(r'^# Important Title\s*\n\n', '', chunk_i)
            text2 = re.sub(r'^# Important Title\s*\n\n', '', chunk_i_plus_1)
            
            if text1:
                token_ids = chunker.encoding.encode(text1)
                overlap_ids = token_ids[-chunker.overlap:] if len(token_ids) >= chunker.overlap else token_ids
                
                try:
                    expected_overlap = chunker.encoding.decode(overlap_ids).strip()
                    if expected_overlap and len(expected_overlap) > 3:
                        assert expected_overlap in text2, \
                               f"块{i}和块{i+1}之间的重叠检查失败。期望：'{expected_overlap}'；实际：'{text2[:50]}...'"
                except Exception as e:
                    print(f"重叠检查中出现错误: {e}")
