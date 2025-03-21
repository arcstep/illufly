import argparse
from pathlib import Path
from scripts.base_model import ModelConfig, BaseModel, QwenCoder, create_base_parser, create_model_config
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
        history = self._format_history()
        if history:
            return f"""以下是之前的对话历史：

{history}

用户：{query}
助手："""
        return f"用户：{query}\n助手："

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

    def _generate_modelfile(self, model_path: str = None) -> str:
        return f'''FROM {model_path if model_path else self.model_name}
LICENSE Apache 2.0
TEMPLATE """
你是一个编程助手，请帮助用户解决编程相关问题。
请简洁直接地回答问题，回答完成后输出"<END>"表示结束。

{{{{.Prompt}}}}
"""

PARAMETER temperature {self.config.temperature}
PARAMETER top_p {self.config.top_p}
PARAMETER stop "<END>"'''

    def _create_ollama_model(self) -> bool:
        """创建 Ollama 模型"""
        # 对于 Qwen，我们可以直接从 HuggingFace 拉取
        return True  # Ollama 会自动处理

def main():
    # 创建解析器并添加特定参数
    parser = create_base_parser("Qwen Coder 编程助手")
    parser.add_argument('--language', default="python", help="默认编程语言")
    args = parser.parse_args()
    
    # 设置默认值
    if not args.model_id:
        args.model_id = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    
    # 创建模型配置
    config = create_model_config(args)
    
    # 创建模型实例
    coder = EnhancedQwenCoder(
        args.model_id,
        use_llama=(args.backend == 'llama'),
        use_ollama=(args.backend == 'ollama'),
        config=config
    )
    
    # 设置默认语言
    coder.current_language = args.language

    # 开始交互式会话
    coder.interactive_session()

if __name__ == "__main__":
    main()