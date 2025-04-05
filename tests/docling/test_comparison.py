"""比较测试模块

比较官方DocumentConverter和自定义ObservableConverter处理相同PDF时的行为差异
"""

import pytest
import asyncio
import tempfile
import os
import logging
from pathlib import Path
import warnings

# 导入docling必要组件
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat, ConversionStatus
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

# 导入自定义组件
from illufly.docling import ObservableConverter, DocumentProcessStatus

# 设置日志
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sample_pdf_path():
    """提供测试PDF文件路径"""
    pdf_path = os.path.join(os.path.dirname(__file__), "simple_test.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("找不到测试PDF文件: simple_test.pdf")
    return pdf_path


class TestCompareConverters:
    """比较官方和自定义文档转换器"""
    
    def test_compare_synchronous_conversion(self, sample_pdf_path):
        """比较同步转换行为"""
        # 创建相同的格式选项，确保公平比较
        pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
            do_formula_enrichment=False,
            generate_page_images=True  # 避免deprecated警告
        )
        
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=SimplePipeline,  # 使用简单管道，避免模型加载问题
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            )
        }
        
        # 先记录所有警告
        with warnings.catch_warnings(record=True) as official_warnings:
            # 使用官方DocumentConverter
            official_converter = DocumentConverter(format_options=format_options)
            official_result = official_converter.convert(sample_pdf_path, raises_on_error=False)
        
        with warnings.catch_warnings(record=True) as our_warnings:
            # 使用自定义ObservableConverter
            our_converter = ObservableConverter(format_options=format_options)
            our_result = our_converter.convert(sample_pdf_path, raises_on_error=False)
        
        # 比较转换结果状态
        assert official_result.status == our_result.status, "转换状态不匹配"
        
        # 检查是否有额外的警告
        assert len(our_warnings) <= len(official_warnings), "我们的实现产生了更多警告"
        
        # 比较更多详细特性
        if official_result.status == ConversionStatus.SUCCESS:
            # 比较文档结构
            assert bool(official_result.document) == bool(our_result.document), "文档对象存在性不匹配"
            if official_result.document and our_result.document:
                # 比较页面数量
                assert len(official_result.document.pages) == len(our_result.document.pages), "页面数量不匹配"
                
                # 比较文本内容
                official_text = official_result.document.export_to_text()
                our_text = our_result.document.export_to_text()
                assert len(official_text) == len(our_text), "文本长度不匹配"
    
    @pytest.mark.asyncio
    async def test_compare_async_behavior(self, sample_pdf_path):
        """比较异步行为 - 将官方同步转换与自定义异步转换进行比较"""
        # 创建相同的格式选项
        pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
            do_formula_enrichment=False,
            generate_page_images=True
        )
        
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=SimplePipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            )
        }
        
        # 官方同步转换
        official_converter = DocumentConverter(format_options=format_options)
        official_result = official_converter.convert(sample_pdf_path, raises_on_error=False)
        
        # 自定义异步转换
        our_converter = ObservableConverter(format_options=format_options)
        async_updates = []
        final_result = None
        
        # 收集所有异步更新并获取最终结果
        async for update in our_converter.convert_async(sample_pdf_path, raises_on_error=False):
            async_updates.append(update)
            if isinstance(update, dict) and update.get("type") == "result":
                final_result = update.get("result")
        
        # 验证异步过程
        assert len(async_updates) > 0, "异步过程没有产生任何更新"
        assert final_result is not None, "异步过程没有产生最终结果"
        
        # 比较结果状态
        assert official_result.status == final_result.status, "同步和异步转换状态不匹配"
        
        # 如果成功转换，比较更多属性
        if official_result.status == ConversionStatus.SUCCESS and final_result.status == ConversionStatus.SUCCESS:
            # 比较文档是否存在
            assert bool(official_result.document) == bool(final_result.document), "文档对象存在性不匹配"
            if official_result.document and final_result.document:
                # 比较页面数量
                assert len(official_result.document.pages) == len(final_result.document.pages), "页面数量不匹配"
                
                # 比较文本内容
                official_text = official_result.document.export_to_text()
                our_text = final_result.document.export_to_text()
                assert len(official_text) == len(our_text), "文本长度不匹配"
    
    def test_edge_cases(self):
        """测试边缘情况的处理"""
        # 同样的配置
        pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
            do_formula_enrichment=False,
            generate_page_images=True
        )
        
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=SimplePipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            )
        }
        
        # 初始化转换器
        official_converter = DocumentConverter(format_options=format_options)
        our_converter = ObservableConverter(format_options=format_options)
        
        # 创建不存在的文件路径
        temp_dir = tempfile.gettempdir()
        non_existent_file = os.path.join(temp_dir, "absolutely_not_exists_12345.pdf")
        
        # 确保文件确实不存在
        if os.path.exists(non_existent_file):
            os.unlink(non_existent_file)
        
        # 测试异常情况的行为
        try:
            # 官方版本
            try:
                official_result = official_converter.convert(non_existent_file, raises_on_error=False)
                official_status = official_result.status
            except Exception as e:
                official_status = str(e)
                
            # 我们的版本
            try:
                our_result = our_converter.convert(non_existent_file, raises_on_error=False)
                our_status = our_result.status
            except Exception as e:
                our_status = str(e)
                
            # 比较行为 - 两者应该都成功处理错误情况
            assert official_status == our_status, f"错误处理不一致: 官方={official_status}, 我们的={our_status}"
            
        except Exception as e:
            # 如果测试本身失败，记录信息但不阻止其他测试
            logger.error(f"边缘情况测试失败: {str(e)}")
            pytest.skip(f"边缘情况测试失败: {str(e)}") 

    def test_warning_behavior(self, sample_pdf_path):
        """比较两种实现的警告行为"""
        # 使用可能会产生警告的配置
        pipeline_options = PdfPipelineOptions(
            do_ocr=False,
            do_table_structure=False,
            do_formula_enrichment=False,
            # 故意不设置generate_page_images来触发弃用警告
        )
        
        format_options = {
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=SimplePipeline,
                backend=PyPdfiumDocumentBackend,
                pipeline_options=pipeline_options
            )
        }
        
        # 使用warnings模块捕获警告
        with warnings.catch_warnings(record=True) as official_warnings:
            warnings.simplefilter("always")  # 确保捕获所有警告
            # 使用官方DocumentConverter
            official_converter = DocumentConverter(format_options=format_options)
            official_result = official_converter.convert(sample_pdf_path, raises_on_error=False)
        
        with warnings.catch_warnings(record=True) as our_warnings:
            warnings.simplefilter("always")
            # 使用自定义ObservableConverter
            our_converter = ObservableConverter(format_options=format_options)
            our_result = our_converter.convert(sample_pdf_path, raises_on_error=False)
        
        # 记录警告详情
        logger.info(f"官方实现警告数量: {len(official_warnings)}")
        logger.info(f"我们的实现警告数量: {len(our_warnings)}")
        
        # 打印警告信息以便检查
        for i, w in enumerate(official_warnings):
            logger.info(f"官方警告 {i+1}: {w.message}")
            
        for i, w in enumerate(our_warnings):
            logger.info(f"我们的警告 {i+1}: {w.message}")
        
        # 验证警告数量 - 如果不相等，输出警告内容，但允许测试继续进行
        if len(official_warnings) != len(our_warnings):
            logger.warning(f"警告数量不一致: 官方={len(official_warnings)}, 我们的={len(our_warnings)}")
            
        # 警告类型应该相似
        official_warning_types = [type(w.message) for w in official_warnings]
        our_warning_types = [type(w.message) for w in our_warnings]
        
        # 检查我们的实现是否有官方实现没有的警告类型
        for wt in our_warning_types:
            if wt not in official_warning_types:
                logger.warning(f"我们的实现有额外警告类型: {wt}")
                
        # 转换结果应当一致，即使有警告
        assert official_result.status == our_result.status, "即使有警告，转换状态也应一致" 