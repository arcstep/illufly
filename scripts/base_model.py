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
        n_gpu_layers: int = 0  # 新增：GPU 层数
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
        
        if use_ollama:
            # 检查 Ollama 服务是否可用
            try:
                response = requests.get(f"{self.config.ollama.url}/api/tags")
                if response.status_code != 200:
                    raise ConnectionError("Ollama 服务未启动")
                print(f"Ollama 服务正常")
                
                # 检查模型是否已存在
                models = response.json().get("models", [])
                model_exists = any(m["name"] == self.config.ollama.model_name for m in models)
                
                if not model_exists:
                    # 如果模型不存在，尝试导入
                    if quantized_path and Path(quantized_path).exists():
                        print(f"正在导入模型到 Ollama: {quantized_path}")
                        self._import_model_to_ollama(quantized_path)
                    else:
                        # 尝试从 Modelfile 创建
                        if self._create_ollama_model():
                            print(f"已创建 Ollama 模型: {self.config.ollama.model_name}")
                        else:
                            raise ValueError("无法创建 Ollama 模型")
                
            except requests.exceptions.ConnectionError:
                print("请先启动 Ollama 服务")
                print("安装说明: https://ollama.ai/download")
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
        params = {
            "model_path": model_path,
            "n_ctx": min(2048, self.config.n_ctx),  # 减小上下文长度
            "n_threads": min(4, self.config.n_threads),  # 减小线程数
            "n_batch": min(128, self.config.n_batch),  # 减小批处理大小
            "use_mlock": False,  # 禁用内存锁定
            "use_mmap": True,
            "vocab_only": False,
            "seed": -1,
            "f16_kv": True,  # 使用 float16 来存储 key 和 value
            "logits_all": False,
            "embedding": False
        }

        if self.config.device == "cpu":
            # CPU 模式
            params.update({
                "n_gpu_layers": 0,
                "use_metal": False,
                "use_cuda": False
            })
        elif self.config.device == "metal" and sys.platform == "darwin":
            # Metal GPU 模式 (仅 Mac)
            params.update({
                "n_gpu_layers": min(1, self.config.n_gpu_layers),  # 先尝试只用1层
                "use_metal": True,
                "use_cuda": False
            })
        elif self.config.device == "cuda":
            # CUDA GPU 模式
            params.update({
                "n_gpu_layers": self.config.n_gpu_layers,
                "use_metal": False,
                "use_cuda": True
            })
        
        try:
            print(f"使用 {self.config.device.upper()} 模式加载模型...")
            print(f"参数配置: {params}")
            self.model = Llama(**params)
        except Exception as e:
            print(f"首次加载失败: {str(e)}")
            print("尝试使用最小配置重新加载...")
            
            # 使用最小配置
            minimal_params = {
                "model_path": model_path,
                "n_ctx": 512,        # 最小上下文
                "n_threads": 1,      # 单线程
                "n_batch": 8,        # 最小批处理
                "use_mlock": False,
                "use_mmap": True,
                "n_gpu_layers": 0,   # 纯 CPU
                "use_metal": False,
                "use_cuda": False,
                "vocab_only": False,
                "f16_kv": True,
                "logits_all": False,
                "embedding": False
            }
            
            try:
                print("使用最小配置加载...")
                self.model = Llama(**minimal_params)
                print("加载成功！可以尝试逐步增加参数值")
            except Exception as e:
                print(f"最小配置加载也失败了: {str(e)}")
                print("请检查：")
                print("1. 模型文件是否完整")
                print("2. 系统可用内存是否充足")
                print("3. 是否有其他程序占用了大量资源")
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

    def generate_stream(self, query: str, **kwargs):
        """流式生成回答"""
        prompt = self._prepare_prompt(query, **kwargs)
        
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
                yield new_text

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
        pass

    def _handle_special_command(self, command: str) -> bool:
        """处理特殊命令，返回是否已处理"""
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