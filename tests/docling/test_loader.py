"""文档加载器测试模块

测试文档加载和格式识别功能
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from illufly.docling import DocumentProcessStatus, DocumentLoader

@pytest.fixture
def status_tracker():
    """创建状态追踪器"""
    return DocumentProcessStatus()

@pytest.fixture
def loader(status_tracker):
    """创建文档加载器"""
    return DocumentLoader(status_tracker)

def test_detect_file_format_local(loader):
    """测试本地文件格式检测"""
    # 测试文档格式
    formats = {
        '.pdf': ('pdf', 'application/pdf'),
        '.docx': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        '.xlsx': ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        '.pptx': ('pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
        '.doc': ('doc', 'application/msword'),
        '.xls': ('xls', 'application/vnd.ms-excel'),
        '.ppt': ('ppt', 'application/vnd.ms-powerpoint'),
        
        # 标记语言
        '.md': ('markdown', 'text/markdown'),
        '.adoc': ('asciidoc', 'text/asciidoc'),
        '.html': ('html', 'text/html'),
        '.htm': ('html', 'text/html'),
        '.xhtml': ('xhtml', 'application/xhtml+xml'),
        
        # 数据格式
        '.csv': ('csv', 'text/csv'),
        '.json': ('json', 'application/json'),
        
        # 图片格式
        '.png': ('png', 'image/png'),
        '.jpg': ('jpeg', 'image/jpeg'),
        '.jpeg': ('jpeg', 'image/jpeg'),
        '.tiff': ('tiff', 'image/tiff'),
        '.bmp': ('bmp', 'image/bmp'),
        
        # XML格式
        '.xml': ('xml', 'application/xml'),
        '.uspto': ('xml', 'application/xml'),
        '.jats': ('xml', 'application/xml'),
        
        # 其他
        '.txt': ('txt', 'text/plain')
    }
    
    for ext, (expected_format, expected_mime) in formats.items():
        with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
            format_type, mime_type = loader._detect_file_format(tmp.name)
            assert format_type == expected_format
            assert mime_type == expected_mime

def test_detect_file_format_url_extension(loader):
    """测试URL扩展名格式检测"""
    # 测试文档格式URL
    urls = {
        'https://example.com/document.pdf': ('pdf', 'application/pdf'),
        'https://example.com/document.docx': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        'https://example.com/document.xlsx': ('xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        'https://example.com/document.pptx': ('pptx', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'),
        'https://example.com/document.doc': ('doc', 'application/msword'),
        'https://example.com/document.xls': ('xls', 'application/vnd.ms-excel'),
        'https://example.com/document.ppt': ('ppt', 'application/vnd.ms-powerpoint'),
        
        # 测试标记语言URL
        'https://example.com/document.md': ('markdown', 'text/markdown'),
        'https://example.com/document.adoc': ('asciidoc', 'text/asciidoc'),
        'https://example.com/document.html': ('html', 'text/html'),
        'https://example.com/document.htm': ('html', 'text/html'),
        'https://example.com/document.xhtml': ('xhtml', 'application/xhtml+xml'),
        
        # 测试图片URL
        'https://example.com/image.png': ('png', 'image/png'),
        'https://example.com/image.jpg': ('jpeg', 'image/jpeg'),
        'https://example.com/image.jpeg': ('jpeg', 'image/jpeg'),
        'https://example.com/image.tiff': ('tiff', 'image/tiff'),
        'https://example.com/image.bmp': ('bmp', 'image/bmp'),
        
        # 测试XML URL
        'https://example.com/document.xml': ('xml', 'application/xml'),
        'https://example.com/document.uspto': ('xml', 'application/xml'),
        'https://example.com/document.jats': ('xml', 'application/xml'),
        
        # 测试arxiv PDF URL
        'https://arxiv.org/pdf/2503.21760': ('pdf', 'application/pdf')
    }
    
    for url, (expected_format, expected_mime) in urls.items():
        format_type, mime_type = loader._detect_file_format(url)
        assert format_type == expected_format
        assert mime_type == expected_mime

@patch('requests.head')
def test_detect_file_format_url_content_type(mock_head, loader):
    """测试URL Content-Type格式检测"""
    # 测试各种Content-Type
    content_types = {
        'application/pdf': ('pdf', 'application/pdf'),
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ('docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        'text/markdown': ('markdown', 'text/markdown'),
        'text/asciidoc': ('asciidoc', 'text/asciidoc'),
        'text/html': ('html', 'text/html'),
        'image/png': ('png', 'image/png'),
        'application/xml': ('xml', 'application/xml'),
        'text/plain': ('txt', 'text/plain')
    }
    
    for content_type, (expected_format, expected_mime) in content_types.items():
        mock_response = MagicMock()
        mock_response.headers = {'Content-Type': content_type}
        mock_head.return_value = mock_response
        
        format_type, mime_type = loader._detect_file_format('https://example.com/document')
        assert format_type == expected_format
        assert mime_type == expected_mime

def test_load_document_local(loader):
    """测试加载本地文档"""
    # 测试各种文档格式
    formats = ['.pdf', '.docx', '.xlsx', '.pptx', '.doc', '.xls', '.ppt', '.md', '.html', '.csv']
    
    for ext in formats:
        with tempfile.NamedTemporaryFile(suffix=ext) as tmp:
            in_doc, format_type = loader.load_document(tmp.name)
            assert in_doc.file == Path(tmp.name)
            assert format_type in loader._supported_formats

def test_load_document_with_metadata(loader):
    """测试带元数据的文档加载"""
    metadata = {'title': '测试文档', 'author': '测试作者'}
    
    with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:
        in_doc, _ = loader.load_document(tmp.name, metadata=metadata)
        assert in_doc.metadata == metadata

def test_download_document(loader):
    """测试文档下载"""
    # 测试各种文档格式
    urls = [
        'https://example.com/test.pdf',
        'https://example.com/test.docx',
        'https://example.com/test.xlsx',
        'https://example.com/test.md',
        'https://example.com/test.html'
    ]
    
    for url in urls:
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = loader.download_document(url, save_path=os.path.join(tmpdir, os.path.basename(url)))
            assert os.path.exists(save_path)
            assert os.path.basename(save_path) == os.path.basename(url)

def test_download_document_error(loader):
    """测试文档下载错误处理"""
    # 使用无效URL
    invalid_url = 'https://invalid-url.example.com/nonexistent.pdf'
    
    with pytest.raises(Exception):
        loader.download_document(invalid_url)
    
    # 验证状态更新
    assert loader.status_tracker.failed
    assert '下载失败' in loader.status_tracker.error_message 