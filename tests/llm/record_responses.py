import os
import json
from pathlib import Path
import asyncio
from datetime import datetime
from illufly.llm.chat_qwen import ChatQwen

RECORDINGS_DIR = Path(__file__).parent / "fixtures" / "chat_qwen" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

async def record_scenario(name: str, config: dict):
    """录制单个场景的响应"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = RECORDINGS_DIR / f"{name}_{timestamp}.json"
    
    chat = ChatQwen(**config.get("chat_config", {}))
    responses = []
    
    try:
        messages = config["messages"]
        async for block in chat(messages):
            responses.append(block.model_dump())
    except Exception as e:
        responses.append({
            "type": "error",
            "content": str(e)
        })
    
    # 保存录制的响应
    with output_file.open("w", encoding="utf-8") as f:
        json.dump({
            "scenario": name,
            "config": config,
            "responses": responses
        }, f, ensure_ascii=False, indent=2)
    
    print(f"Recorded scenario '{name}' to {output_file}")

async def record_all_scenarios():
    """录制所有预定义的场景"""
    scenarios = {
        "normal_chat": {
            "chat_config": {
                "api_key": os.getenv("DASHSCOPE_API_KEY")
            },
            "messages": [{"role": "user", "content": "你好"}]
        },
        "invalid_token": {
            "chat_config": {
                "api_key": "invalid_key"
            },
            "messages": [{"role": "user", "content": "你好"}]
        },
        "token_exceeded": {
            "chat_config": {
                "api_key": os.getenv("DASHSCOPE_API_KEY")
            },
            "messages": [{"role": "user", "content": "测试" * 5000}]
        }
    }
    
    for name, config in scenarios.items():
        await record_scenario(name, config)

if __name__ == "__main__":
    asyncio.run(record_all_scenarios()) 