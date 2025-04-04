from abc import ABC, abstractmethod
import threading
import sys
from pathlib import Path
from typing import Optional, Union, Dict
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from llama_cpp import Llama
from huggingface_hub import try_to_load_from_cache
from transformers.utils import WEIGHTS_NAME, CONFIG_NAME
import json
import requests
from dataclasses import dataclass
import os
import argparse

@dataclass
class OllamaConfig:
    """Ollama 配置"""
    url: str = "http://localhost:11434"
    model_name: str = ""  # 在 Ollama 中的模型名称
    stop_words: list = None  # 停止词

class ModelConfig:
    def __init__(
        self,
        cache_dir: str = "models",
        llama_cpp_dir: str = "llama.cpp",
        n_ctx: int = 4096,
        n_threads: int = 6,
        n_batch: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        max_tokens: int = 512,
        device: str = "cpu",  # 新增：明确指定设备
        n_gpu_layers: int = 0,  # 新增：GPU 层数
        max_history: int = 5,  # 新增：最大历史对话轮数
    ):
        self.cache_dir = Path(cache_dir)
        self.llama_cpp_dir = Path(llama_cpp_dir)
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_batch = n_batch
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.device = device.lower()
        self.n_gpu_layers = n_gpu_layers
        self.max_history = max_history

@dataclass
class ModelArguments:
    """模型运行参数"""
    model_id: str
    backend: str = "hf"      # hf/llama/ollama
    device: str = "cpu"      # cpu/metal/cuda
    n_ctx: int = 512        # 上下文长度
    n_threads: int = 1      # 线程数
    n_batch: int = 8        # 批处理大小
    cache_dir: str = "models"
    llama_cpp_dir: str = "llama.cpp"
    quantization: str = "q4_0"
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 512
    n_gpu_layers: int = 0

def create_base_parser(description: str) -> argparse.ArgumentParser:
    """创建基础命令行参数解析器"""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--model_id', help="模型ID")
    parser.add_argument('--backend', choices=['hf', 'llama', 'ollama'], default='hf', 
                       help="运行后端：hf/llama/ollama")
    parser.add_argument('--device', choices=['cpu', 'metal', 'cuda'], default='cpu', 
                       help="设备类型：cpu/metal(Mac)/cuda")
    parser.add_argument('--n_ctx', type=int, default=512, help="上下文长度")
    parser.add_argument('--n_threads', type=int, default=1, help="线程数")
    parser.add_argument('--n_batch', type=int, default=8, help="批处理大小")
    parser.add_argument('--cache_dir', default="models", help="模型缓存目录")
    parser.add_argument('--llama_cpp_dir', default="llama.cpp", help="llama.cpp目录")
    parser.add_argument('--quantization', default="q4_0", help="量化类型")
    parser.add_argument('--temperature', type=float, default=0.7, help="采样温度")
    parser.add_argument('--top_p', type=float, default=0.95, help="Top-p采样")
    parser.add_argument('--max_tokens', type=int, default=512, help="最大生成长度")
    parser.add_argument('--n_gpu_layers', type=int, default=0, help="GPU层数")
    parser.add_argument('--max_history', type=int, default=5, help="最大历史对话轮数")
    return parser

def create_model_config(args: ModelArguments) -> ModelConfig:
    """根据参数创建模型配置"""
    config = ModelConfig(
        cache_dir=args.cache_dir,
        llama_cpp_dir=args.llama_cpp_dir,
        n_ctx=args.n_ctx,
        n_threads=args.n_threads,
        n_batch=args.n_batch,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        device=args.device,
        n_gpu_layers=args.n_gpu_layers,
        max_history=args.max_history
    )
    
    if args.backend == 'ollama':
        # 根据模型类型设置不同的名称
        model_name = args.model_id.split('/')[-1].lower()
        config.ollama = OllamaConfig(
            model_name=model_name,
            stop_words=["<END>"]
        )
    
    return config

class BaseModel(ABC):
    def __init__(
        self,
        model_name: str,
        use_llama: bool = False,
        use_ollama: bool = False,
        quantized_path: Optional[str] = None,
        device: str = "auto",
        config: Optional[ModelConfig] = None
    ):
        """
        初始化模型
        Args:
            model_name: 模型名称或路径
            use_llama: 是否使用llama.cpp
            use_ollama: 是否使用 Ollama
            quantized_path: 量化模型路径，如果为None则使用原始模型
            device: 设备类型，auto/cpu/cuda
        """
        self.model_name = model_name
        self.use_llama = use_llama
        self.use_ollama = use_ollama
        self.config = config or ModelConfig()
        
        if use_ollama and use_llama:
            raise ValueError("不能同时使用 llama.cpp 和 Ollama")

        # 确保目录存在
        self.config.cache_dir.mkdir(exist_ok=True)
        
        self.conversation_history = []  # 添加对话历史列表
        self.max_history = 5  # 默认保留最近5轮对话
        
        if use_ollama:
            if not self._setup_ollama(quantized_path):
                sys.exit(1)
        elif use_llama:
            model_loaded = False
            
            # 1. 检查指定的量化模型
            if quantized_path and Path(quantized_path).exists():
                print(f"加载指定的量化模型: {quantized_path}")
                self._load_llama_model(quantized_path)
                model_loaded = True
            
            # 2. 检查是否有现成的量化版本
            if not model_loaded:
                quantized_path = self._find_quantized_model()
                if quantized_path and Path(quantized_path).exists():
                    print(f"加载已有的量化模型: {quantized_path}")
                    self._load_llama_model(quantized_path)
                    model_loaded = True
            
            # 3. 尝试转换和量化
            if not model_loaded:
                original_path = self._find_original_model()
                if original_path:
                    quantized_path = self._convert_and_quantize(original_path)
                    if quantized_path and Path(quantized_path).exists():
                        print(f"加载新量化的模型: {quantized_path}")
                        self._load_llama_model(quantized_path)
                        model_loaded = True
            
            if not model_loaded:
                print("请按照上述提示完成模型转换和量化后重试")
                sys.exit(1)
        else:
            print(f"加载原始模型: {model_name}")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype="auto",
                device_map=device
            )
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def _load_llama_model(self, model_path: str):
        """加载 llama.cpp 模型"""
        # 基础参数
        params = {
            "model_path": model_path,
            "n_ctx": self.config.n_ctx,
            "n_threads": self.config.n_threads,
            "n_batch": self.config.n_batch,
            "use_mlock": False,
            "use_mmap": True,
            "vocab_only": False,
            "seed": -1,
            "f16_kv": True,
            "logits_all": False,
            "embedding": False
        }

        # 根据设备类型设置加速参数
        if self.config.device == "cpu":
            params.update({
                "n_gpu_layers": 0,
                "use_metal": False,
                "use_cuda": False
            })
        elif self.config.device == "metal":
            params.update({
                "n_gpu_layers": self.config.n_gpu_layers,
                "use_metal": True,
                "use_cuda": False
            })
        elif self.config.device == "cuda":
            params.update({
                "n_gpu_layers": self.config.n_gpu_layers,
                "use_metal": False,
                "use_cuda": True
            })
        
        try:
            print(f"使用 {self.config.device.upper()} 模式加载模型...")
            print(f"参数配置: {params}")
            self.model = Llama(**params)
            print("✓ 模型加载成功！")
        except Exception as e:
            error_msg = str(e)
            print(f"模型加载失败: {error_msg}")
            
            # 根据错误类型给出具体建议
            if "Metal" in error_msg:
                print("\n建议：")
                print("1. 检查是否支持 Metal API")
                print("2. 尝试使用 CPU 模式: --device cpu")
                print("3. 或者使用 Ollama: --backend ollama")
            elif "CUDA" in error_msg:
                print("\n建议：")
                print("1. 检查 CUDA 环境")
                print("2. 尝试使用 CPU 模式: --device cpu")
                print("3. 或者使用 Ollama: --backend ollama")
            else:
                print("\n可能的原因：")
                print("1. 内存不足")
                print("2. 模型文件损坏")
                print("3. 硬件不支持")
                print("\n建议：")
                print("1. 减小参数：")
                print("   --n_ctx 512 --n_threads 1 --n_batch 8")
                print("2. 使用较小的量化模型：")
                print("   --quantization q4_0")
                print("3. 或者使用 Ollama：")
                print("   --backend ollama")
            raise

    def _find_original_model(self) -> Optional[str]:
        """查找原始模型"""
        # 尝试找到配置文件
        config_path = try_to_load_from_cache(self.model_name, CONFIG_NAME)
        if config_path:
            model_path = Path(config_path).parent
            print(f"✓ 已找到缓存模型: {model_path}")
            return str(model_path)
        
        # 尝试在默认缓存目录中查找
        cache_dir = Path.home() / ".cache/huggingface/hub"
        if cache_dir.exists():
            model_id_path = self.model_name.replace('/', '--')
            for path in cache_dir.glob(f"**/{model_id_path}*/pytorch_model.bin"):
                print(f"✓ 已找到缓存模型: {path.parent}")
                return str(path.parent)
        
        print("✗ 未找到缓存模型，请先下载：")
        print(f"huggingface-cli download {self.model_name}")
        return None

    def _convert_and_quantize(self, model_path: str) -> Optional[str]:
        """转换并量化模型"""
        llama_cpp = self.config.llama_cpp_dir
        
        # 检查 llama.cpp 环境
        if not self._check_llama_cpp():
            return None
            
        # 转换为 GGUF
        gguf_path = self.config.cache_dir / "model-f16.gguf"
        if not gguf_path.exists():
            print("\n=== 转换为GGUF格式 ===")
            cmd = f"python {llama_cpp}/convert_hf_to_gguf.py --outfile {gguf_path} --outtype f16 {model_path}"
            print(f"请执行转换命令:\n{cmd}")
            return None
            
        # 量化
        quantized_path = self._get_quantized_path()
        if not quantized_path.exists():
            print("\n=== 执行量化 ===")
            cmd = f"{llama_cpp}/build/bin/llama-quantize {gguf_path} {quantized_path} q8_0"
            print(f"请执行量化命令:\n{cmd}")
            return None
            
        return str(quantized_path)

    def _check_llama_cpp(self) -> bool:
        """检查 llama.cpp 环境"""
        llama_cpp = self.config.llama_cpp_dir
        if not llama_cpp.exists():
            print("\n=== 准备llama.cpp ===")
            print("请克隆llama.cpp:")
            print("git clone https://github.com/ggerganov/llama.cpp.git")
            print("\n然后使用CMake编译:")
            print("cd llama.cpp")
            print("cmake -B build")
            print("cmake --build build --config Release")
            return False
            
        if not (llama_cpp / "build/bin/llama-quantize").exists():
            print("\n请编译llama.cpp:")
            print(f"cd {llama_cpp}")
            print("cmake -B build")
            print("cmake --build build --config Release")
            return False
            
        return True

    @abstractmethod
    def _find_quantized_model(self) -> Optional[str]:
        """查找预先量化的模型"""
        pass

    @abstractmethod
    def _get_quantized_path(self) -> Path:
        """获取量化模型的保存路径"""
        pass

    @abstractmethod
    def _prepare_prompt(self, query: str, **kwargs) -> str:
        """准备提示词"""
        pass

    def _import_model_to_ollama(self, model_path: str):
        """导入模型到 Ollama"""
        modelfile = self._generate_modelfile(model_path)
        modelfile_path = self.config.cache_dir / "Modelfile"
        modelfile_path.write_text(modelfile)
        
        # 创建模型
        cmd = f"ollama create {self.config.ollama.model_name} -f {modelfile_path}"
        print(f"执行命令: {cmd}")
        os.system(cmd)

    def _create_ollama_model(self) -> bool:
        """创建 Ollama 模型"""
        return False  # 基类默认不实现，由子类实现具体逻辑

    @abstractmethod
    def _generate_modelfile(self, model_path: str = None) -> str:
        """生成 Modelfile 内容"""
        pass

    def _add_to_history(self, role: str, content: str):
        """添加消息到对话历史"""
        self.conversation_history.append({"role": role, "content": content})
        # 保持历史记录在最大长度以内
        if len(self.conversation_history) > self.max_history * 2:  # 每轮对话有用户和助手两条消息
            self.conversation_history = self.conversation_history[-self.max_history * 2:]

    def generate_stream(self, query: str, **kwargs):
        """流式生成回答"""
        # 将用户问题添加到历史
        self._add_to_history("user", query)
        
        # 准备带有历史记录的提示词
        prompt = self._prepare_prompt(query, **kwargs)
        
        response_text = ""
        if self.use_ollama:
            # Ollama 的流式输出
            response = requests.post(
                f"{self.config.ollama.url}/api/generate",
                json={
                    "model": self.config.ollama.model_name,
                    "prompt": prompt,
                    "stream": True,
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    **({"stop": self.config.ollama.stop_words} if self.config.ollama.stop_words else {})
                },
                stream=True
            )
            
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        chunk = json.loads(line)
                        if not chunk.get('done', False):
                            response_text += chunk['response']
                            yield chunk['response']
            else:
                raise Exception(f"Ollama API 错误: {response.text}")
                
        elif self.use_llama:
            # llama.cpp 的流式输出
            response = self.model.create_completion(
                prompt,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                stream=True
            )
            
            for chunk in response:
                chunk_text = chunk['choices'][0]['text']
                response_text += chunk_text
                yield chunk_text
                
        else:
            # HuggingFace 的流式输出
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

            streamer = TextIteratorStreamer(
                self.tokenizer,
                skip_special_tokens=True,
                skip_prompt=True
            )
            
            def generate():
                with torch.no_grad():
                    self.model.generate(
                        **model_inputs,
                        max_new_tokens=self.config.max_tokens,
                        temperature=self.config.temperature,
                        top_p=self.config.top_p,
                        do_sample=True,
                        streamer=streamer,
                    )
            
            thread = threading.Thread(target=generate)
            thread.start()

            for new_text in streamer:
                response_text += new_text
                yield new_text

        # 将助手的回答添加到历史
        self._add_to_history("assistant", response_text)

    def interactive_session(self):
        """交互式会话"""
        self._show_welcome_message()
        
        while True:
            try:
                query = input("\n请输入问题: ").strip()
                if query.lower() in ["exit", "quit", "bye", "q"]:
                    break
                if not query:
                    continue
                
                # 处理特殊命令
                if self._handle_special_command(query):
                    continue
                
                print("\n回答: ", end="", flush=True)
                for chunk in self.generate_stream(query):
                    print(chunk, end="", flush=True)
                print("\n")
                
            except KeyboardInterrupt:
                print("\n会话被用户中断")
                break
            except Exception as e:
                print(f"\n错误: {str(e)}")
                continue
        
        print("再见！")

    def _show_welcome_message(self):
        """显示欢迎信息"""
        print("\n=== 开始交互式问答 ===")
        print("输入 q、exit 或 quit 退出")
        self._show_special_commands()

    def _show_special_commands(self):
        """显示特殊命令说明"""
        super()._show_special_commands()
        print("/clear 或 /c - 清除对话历史")

    def _handle_special_command(self, command: str) -> bool:
        """处理特殊命令"""
        if command.lower() in ["/clear", "/c"]:
            self.clear_history()
            return True
        return False

    def _format_history(self) -> str:
        """格式化对话历史"""
        formatted = []
        for msg in self.conversation_history[:-1]:  # 不包含最新的用户问题
            role = "用户" if msg["role"] == "user" else "助手"
            formatted.append(f"{role}：{msg['content']}")
        return "\n\n".join(formatted)

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        print("已清除对话历史")

    def _setup_ollama(self, quantized_path: Optional[str] = None):
        """设置 Ollama 环境"""
        try:
            # 检查 Ollama 服务
            response = requests.get(f"{self.config.ollama.url}/api/tags")
            if response.status_code != 200:
                raise ConnectionError("Ollama 服务未启动")
            print(f"Ollama 服务正常")
            
            # 检查模型是否存在
            models = response.json().get("models", [])
            model_exists = any(m["name"] == self.config.ollama.model_name for m in models)
            
            if not model_exists:
                print(f"\n=== 创建 Ollama 模型：{self.config.ollama.model_name} ===")
                
                # 1. 如果提供了量化模型路径，使用该路径
                if quantized_path and Path(quantized_path).exists():
                    model_path = Path(quantized_path)
                    print(f"使用指定的量化模型: {model_path}")
                else:
                    # 2. 否则查找或创建量化模型
                    model_path = self._get_quantized_path()
                    if not model_path.exists():
                        print("✗ 未找到量化模型，请先完成模型量化")
                        return False
                
                # 创建 Modelfile
                modelfile = self._generate_modelfile(str(model_path.absolute()))
                modelfile_path = self.config.cache_dir / "Modelfile"
                modelfile_path.write_text(modelfile)
                print(f"已创建 Modelfile: {modelfile_path}")
                
                # 创建模型
                cmd = f"ollama create {self.config.ollama.model_name} -f {modelfile_path}"
                print(f"执行命令: {cmd}")
                result = os.system(cmd)
                
                if result != 0:
                    print("✗ 模型创建失败")
                    return False
                
                print(f"✓ 模型创建成功: {self.config.ollama.model_name}")
            else:
                print(f"✓ 模型已存在: {self.config.ollama.model_name}")
            
            return True
            
        except requests.exceptions.ConnectionError:
            print("请先启动 Ollama 服务")
            print("安装说明: https://ollama.ai/download")
            return False

# Qwen Coder 实现
class QwenCoder(BaseModel):
    def _find_quantized_model(self) -> Optional[str]:
        # 检查是否有官方量化版本
        quantized_name = f"{self.model_name}-gguf"
        if Path(quantized_name).exists():
            return str(quantized_name)
        return None

    def _get_quantized_path(self) -> Path:
        return self.config.cache_dir / "model-f16.gguf"

    def _prepare_prompt(self, query: str, **kwargs) -> str:
        return query

# TableGPT 实现
class TableGPT(BaseModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_df = None

    def _find_quantized_model(self) -> Optional[str]:
        # 检查本地是否有量化版本
        local_path = Path("./models/tablegpt-7b-q8_0.gguf")
        if local_path.exists():
            return str(local_path)
        return None

    def _get_quantized_path(self) -> Path:
        return self.config.cache_dir / "model-f16.gguf"

    def _prepare_prompt(self, query: str, df=None, **kwargs) -> str:
        if df is not None:
            self.current_df = df
            
        if self.current_df is None:
            raise ValueError("请先设置数据框")
            
        table_data = self.current_df.head(10).to_string(index=False)
        stats_info = self.current_df.describe().round(2).to_string()
        
        return f"""根据以下表格数据和统计信息，回答用户的问题。

表格数据：
{table_data}

统计信息：
{stats_info}

问题：{query}
"""

# 使用示例
if __name__ == "__main__":
    # 使用 Qwen Coder
    qwen = QwenCoder("Qwen/Qwen2.5-Coder-1.5B-Instruct")
    qwen.interactive_session()
    
    # 使用 TableGPT
    table_gpt = TableGPT(
        "tablegpt/TableGPT2-7B",
        use_llama=True,
        quantized_path="./models/tablegpt-7b-q8_0.gguf"
    )
    
    # 设置数据
    import pandas as pd
    df = pd.DataFrame({
        "A": [1, 2, 3],
        "B": ["a", "b", "c"]
    })
    table_gpt.current_df = df
    
    table_gpt.interactive_session()