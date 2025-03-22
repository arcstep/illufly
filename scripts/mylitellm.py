import sys
import locale
import dotenv
import os
import sys
from litellm import completion

dotenv.load_dotenv()

# 可以在 completion 中设置 api_key 和 base_url 参数
# 如果是 openai 兼容模型可以在模型设置时增加 openai 前缀作为 provider： "openai/qwen-plus"
response = completion(
    api_key=os.getenv("QWEN_API_KEY"),
    base_url=os.getenv("QWEN_BASE_URL"),
    model="openai/qwen-plus",
    messages=[{"content": "你是什么模型?", "role": "user"}],
    stream=True
)

for chunk in response:
    try:
        # 检查是否有内容
        if "choices" in chunk and len(chunk["choices"]) > 0:
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content")
            # 只有当 content 存在且不为 None 时才打印
            if content is not None:
                print(content, end="", flush=True)
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)

print()  # 打印最后的换行
