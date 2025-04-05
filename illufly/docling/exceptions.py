"""异常类定义

定义docling处理过程中的各种异常类型。
"""


class PipelineError(Exception):
    """管道处理错误基类
    
    所有与文档处理管道相关的错误的基类。
    """
    pass


class ResourceInitError(PipelineError):
    """资源初始化错误
    
    表示在处理过程中初始化资源失败的错误，如无法加载模型、创建处理器等。
    """
    pass


class ProcessingError(PipelineError):
    """处理过程错误
    
    表示在文档处理过程中发生的错误，如解析失败、转换失败等。
    """
    pass 