#!/usr/bin/env python3
"""下载 Docling 所需模型的脚本"""

import os
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download, login
import requests
import shutil
import argparse
import logging
from typing import Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
_log = logging.getLogger(__name__)

# 模型配置
MODELS = {
    "layout": {
        "repo_id": "ds4sd/LayoutModel",
        "filename": "model.safetensors",
        "local_dir": "layout",
        "requires_auth": True
    },
    "document_figure_classifier": {
        "repo_id": "ds4sd/DocumentFigureClassifier",
        "filename": "model.safetensors",
        "local_dir": "document_figure_classifier",
        "requires_auth": False
    },
    "code_formula": {
        "repo_id": "ds4sd/CodeFormula",
        "filename": "model.safetensors",
        "local_dir": "code_formula",
        "requires_auth": False
    },
    "easyocr": {
        "urls": [
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.7.1/craft_mlt_25k.pth",
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.7.0/craft_mlt_25k.pth",
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.6.2/craft_mlt_25k.pth",
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.6.1/craft_mlt_25k.pth",
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.6.0/craft_mlt_25k.pth",
            "https://github.com/JaidedAI/EasyOCR/releases/download/v1.5.0/craft_mlt_25k.pth"
        ],
        "local_dir": "easyocr",
        "filename": "craft_mlt_25k.pth"
    }
}

def download_from_huggingface(repo_id: str, filename: str, local_dir: str, output_dir: Path, requires_auth: bool = False, force: bool = False):
    """从 Hugging Face 下载模型文件"""
    local_path = output_dir / local_dir / filename
    if local_path.exists() and not force:
        _log.info(f"模型已存在: {local_path}")
        return True
        
    _log.info(f"正在从 {repo_id} 下载 {filename}...")
    try:
        token = os.getenv("HUGGINGFACE_TOKEN")
        if requires_auth and not token:
            _log.warning(f"跳过 {repo_id}，需要 Hugging Face 认证")
            return False
            
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=output_dir / local_dir,
            local_dir_use_symlinks=False,
            token=token if requires_auth else None
        )
        _log.info(f"下载完成: {local_path}")
        return True
    except Exception as e:
        _log.error(f"下载失败: {str(e)}")
        if requires_auth:
            _log.warning("提示: 此模型需要 Hugging Face 认证，请设置 HUGGINGFACE_TOKEN 环境变量")
        return False

def download_easyocr_model(output_dir: Path, force: bool = False):
    """下载 EasyOCR 模型文件"""
    local_path = output_dir / "easyocr" / "craft_mlt_25k.pth"
    if local_path.exists() and not force:
        _log.info(f"EasyOCR 模型已存在: {local_path}")
        return True
        
    os.makedirs(output_dir / "easyocr", exist_ok=True)
    
    for url in MODELS["easyocr"]["urls"]:
        _log.info(f"尝试从 {url} 下载 EasyOCR 模型...")
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            _log.info(f"下载完成: {local_path}")
            return True
        except Exception as e:
            _log.error(f"下载失败: {str(e)}")
            continue
    
    _log.error("所有 EasyOCR 模型下载 URL 都失败了，请手动下载并放置到 {local_path}")
    return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="下载 Docling 所需模型")
    parser.add_argument("--token", help="Hugging Face 访问令牌")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/models"), help="模型输出目录")
    parser.add_argument("--force", action="store_true", help="强制重新下载已存在的模型")
    args = parser.parse_args()
    
    # 设置 Hugging Face 令牌
    if args.token:
        os.environ["HUGGINGFACE_TOKEN"] = args.token
        try:
            login(token=args.token)
        except Exception as e:
            _log.error(f"登录失败: {str(e)}")
            _log.warning("将继续尝试下载不需要认证的模型")
    
    # 创建输出目录
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # 下载所有模型
    success_count = 0
    for model_name, model_info in MODELS.items():
        if model_name == "easyocr":
            if download_easyocr_model(args.output_dir, args.force):
                success_count += 1
        else:
            if download_from_huggingface(
                model_info["repo_id"],
                model_info["filename"],
                model_info["local_dir"],
                args.output_dir,
                model_info["requires_auth"],
                args.force
            ):
                success_count += 1
    
    _log.info("\n下载完成！")
    _log.info(f"成功下载 {success_count} 个模型")
    _log.info(f"模型文件位置: {args.output_dir}")
    
    if success_count < len(MODELS):
        _log.warning("\n提示: 有些模型需要 Hugging Face 认证才能下载")
        _log.warning("请设置 HUGGINGFACE_TOKEN 环境变量或使用 --token 参数提供令牌")

if __name__ == "__main__":
    main() 