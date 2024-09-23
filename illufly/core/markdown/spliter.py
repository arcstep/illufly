from typing import Union, List
from ..document import Document

def split_markdown(documents: List[Document], chunk_size: int=None, chunk_overlap: int=None) -> List[Document]:
    """
    按照指定规则分割Markdown文档。

    :param chunk_size: 每个块的大小
    :param chunk_overlap: 每个块的覆盖大小
    :return: 分割后的Document对象列表
    """
    chunk_size = chunk_size or 1024
    chunk_overlap = chunk_overlap or 20

    chunks = []
    current_chunk = []
    source = documents[0].metadata.get('source', 'unknown') if documents else 'unknown'
    heading_stack = []

    def add_chunk():
        if current_chunk:
            chunk_text = ''.join(current_chunk).strip()
            if chunk_text:
                metadata = {'source': source, 'headings': [heading for heading, _ in heading_stack]}
                chunks.append(Document(text=chunk_text, metadata=metadata))
            current_chunk.clear()

    def add_heading_stack():
        for heading, _ in heading_stack:
            current_chunk.append(heading)

    def split_paragraph(text, chunk_size, chunk_overlap):
        paragraphs = text.split('\n')
        para_chunks = []
        for para in paragraphs:
            if len(para) > chunk_size:
                para_chunks.extend(split_markdown([Document(text=para, metadata={'source': source})], chunk_size, chunk_overlap))
            else:
                para_chunks.append(para)
        return para_chunks

    def calculate_text_length(texts):
        return sum(len(text) for text in texts)

    def process_document(doc):
        if doc.metadata['type'] == 'heading':
            if calculate_text_length(current_chunk) + len(doc.text) > chunk_size:
                add_chunk()
                # add_heading_stack()
            heading_level = doc.metadata.get('attrs', {}).get('level', 1)
            while heading_stack and heading_stack[-1][1] >= heading_level:
                heading_stack.pop()
            heading_stack.append((doc.text.strip(), heading_level))
            current_chunk.append(doc.text)
        elif doc.metadata['type'] == 'paragraph':
            if len(doc.text) > chunk_size:
                para_chunks = split_paragraph(doc.text, chunk_size, chunk_overlap)
                current_chunk.extend(para_chunks)
            else:
                current_chunk.append(doc.text)
        else:
            current_chunk.append(doc.text)

        if calculate_text_length(current_chunk) >= chunk_size:
            add_chunk()
            # add_heading_stack()

    def split_by_headings(docs, level=1):
        sub_chunks = []
        current_sub_chunk = []
        for doc in docs:
            if doc.metadata['type'] == 'heading' and doc.metadata.get('attrs', {}).get('level', 1) == level:
                if current_sub_chunk:
                    sub_chunks.append(current_sub_chunk)
                    current_sub_chunk = []
            current_sub_chunk.append(doc)
        if current_sub_chunk:
            sub_chunks.append(current_sub_chunk)
        return sub_chunks

    def recursive_split(docs, level=1):
        sub_chunks = split_by_headings(docs, level)
        for sub_chunk in sub_chunks:
            if calculate_text_length([doc.text for doc in sub_chunk]) > chunk_size:
                if level < 6:  # Assuming maximum heading level is 6
                    recursive_split(sub_chunk, level + 1)
                else:
                    for doc in sub_chunk:
                        process_document(doc)
            else:
                for doc in sub_chunk:
                    process_document(doc)

    recursive_split(documents)
    add_chunk()
    return chunks