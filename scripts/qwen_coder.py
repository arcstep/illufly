import argparse
from pathlib import Path
from scripts.base_model import ModelConfig, BaseModel, QwenCoder
from typing import Optional

class CodePromptMixin:
    """代码生成相关的提示词模板"""
    
    PROMPT_TEMPLATES = {
        "generate": """请生成{language}代码来实现以下功能：
{query}

只需要生成代码，不需要解释。
""",
        "explain": """请解释以下{language}代码的功能：
```{language}
{code}
```
""",
        "optimize": """请优化以下{language}代码，提供改进建议：
```{language}
{code}
```
""",
        "debug": """以下{language}代码存在问题，请帮我找出并修复：
```{language}
{code}
```
"""
    }

class EnhancedQwenCoder(QwenCoder, CodePromptMixin):
    def __init__(self, *args, **kwargs):
        self.default_quantization = "q4_0"  # 默认量化类型
        super().__init__(*args, **kwargs)
        self.current_language = "python"  # 默认语言
        
    def _prepare_prompt(self, query: str, **kwargs) -> str:
        # 检查是否是特殊的代码相关命令
        if query.startswith("!"):
            parts = query[1:].split(" ", 1)
            if len(parts) == 2:
                command, content = parts
                if command in self.PROMPT_TEMPLATES:
                    return self.PROMPT_TEMPLATES[command].format(
                        language=self.current_language,
                        code=content if command != "generate" else query,
                        query=content if command == "generate" else ""
                    )
        
        # 普通查询
        return query

    def _show_special_commands(self):
        """显示特殊命令说明"""
        print("支持的特殊命令：")
        print("- !generate <描述>: 生成代码")
        print("- !explain <代码>: 解释代码")
        print("- !optimize <代码>: 优化代码")
        print("- !debug <代码>: 调试代码")
        print("- !lang <语言>: 切换编程语言（当前：{self.current_language}）")
        print("- !help: 显示帮助信息")

    def _handle_special_command(self, command: str) -> bool:
        """处理特殊命令"""
        if command == "!help":
            self._show_special_commands()
            return True
            
        if command.startswith("!lang "):
            self.current_language = command[6:].strip().lower()
            print(f"\n已切换到 {self.current_language} 语言")
            return True
            
        return False

    def _show_welcome_message(self):
        """显示欢迎信息"""
        print(f"\n=== Qwen Coder 交互式编程助手 ===")
        print(f"当前编程语言: {self.current_language}")
        print("输入 q、exit 或 quit 退出")
        self._show_special_commands()
        print("\n示例：")
        print('!generate "创建一个简单的HTTP服务器"')
        print('!explain "print(\'Hello, World!\')"')

    def _find_quantized_model(self) -> Optional[str]:
        # 首先检查是否有官方量化版本
        quantized_name = f"{self.model_name}-gguf"
        if Path(quantized_name).exists():
            return str(quantized_name)
        
        # 然后检查本地量化版本
        path = self._get_quantized_path()
        return str(path) if path.exists() else None

    def _get_quantized_path(self) -> Path:
        # 使用配置目录和默认量化类型
        return self.config.cache_dir / f"qwen-coder-{self.default_quantization}.gguf"

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
            print("\n转换完成后，请重新运行此脚本")
            return None
            
        # 量化
        quantized_path = self._get_quantized_path()
        if not quantized_path.exists():
            print("\n=== 执行量化 ===")
            cmd = f"{llama_cpp}/build/bin/llama-quantize {gguf_path} {quantized_path} {self.default_quantization}"
            print(f"请执行量化命令:\n{cmd}")
            print("\n量化完成后，请重新运行此脚本")
            return None
            
        return str(quantized_path)

    def _generate_modelfile(self, model_path: str = None) -> str:
        return f'''FROM {model_path if model_path else self.model_name}
PARAMETER temperature {self.config.temperature}
PARAMETER top_p {self.config.top_p}
TEMPLATE """
你是一个编程助手，请帮助用户解决编程相关问题。
{{{{.Prompt}}}}
"""
'''

    def _create_ollama_model(self) -> bool:
        """创建 Ollama 模型"""
        # 对于 Qwen，我们可以直接从 HuggingFace 拉取
        return True  # Ollama 会自动处理

def main():
    parser = argparse.ArgumentParser(description="Qwen Coder 编程助手")
    parser.add_argument('--model_id', default="Qwen/Qwen2.5-Coder-1.5B-Instruct", help="模型ID")
    parser.add_argument('--backend', choices=['hf', 'llama', 'ollama'], default='hf', help="运行后端")
    parser.add_argument('--device', choices=['cpu', 'metal', 'cuda'], default='cpu', 
                       help="设备类型：cpu/metal(Mac)/cuda")
    parser.add_argument('--gpu_layers', type=int, default=0, 
                       help="使用GPU的层数，0表示全CPU")
    args = parser.parse_args()

    # 创建最小配置
    config = ModelConfig(
        cache_dir="models",
        llama_cpp_dir="llama.cpp",
        n_ctx=512,          # 从小值开始
        n_threads=1,        # 单线程
        n_batch=8,          # 小批量
        temperature=0.2,
        top_p=0.95,
        max_tokens=512,     # 限制生成长度
        device="cpu",       # 先用 CPU
        n_gpu_layers=0
    )

    # 创建模型实例
    coder = EnhancedQwenCoder(
        args.model_id,
        use_llama=True,
        device=args.device,
        config=config
    )
    
    # 设置量化类型和默认语言
    coder.default_quantization = "q4_0"
    coder.current_language = "python"

    # 开始交互式会话
    coder.interactive_session()

if __name__ == "__main__":
    main()