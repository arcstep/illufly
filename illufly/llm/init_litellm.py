"""
初始化litellm配置，禁用不必要的网络请求和功能
这个文件应该在导入其他litellm相关模块之前被导入
"""
import os
import litellm

from ..envir import get_env

def init_litellm():
    """
    初始化litellm配置
    
    - 禁用不必要的网络请求
    - 创建缓存目录
    - 启用嵌入和多模态操作的缓存
    """
    
    # 确保缓存目录存在
    cache_dir = get_env("ILLUFLY_CACHE_LITELLM")
    if cache_dir and not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir, exist_ok=True)
            print(f"已创建LiteLLM缓存目录: {cache_dir}")
        except Exception as e:
            print(f"创建缓存目录失败: {e}")
    
    # 为embedding和多模态操作启用缓存
    if cache_dir:
        litellm.enable_cache(
            type="disk",
            disk_cache_dir=cache_dir,
            supported_call_types=[
                "embedding", "aembedding",  # 文本嵌入
                "transcription", "atranscription",  # 语音转文字
                "image_generation", "aimage_generation",  # 图像生成
                "vision", "avision"  # 多模态视觉
            ]
        )

# 在导入时执行初始化
init_litellm() 