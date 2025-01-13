import pytest
import vcr
import os
import json
from pathlib import Path
import argparse
from illufly.llm.chat_qwen import ChatQwen

# 设置录制文件存储路径
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "chat_qwen"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='运行 ChatQwen 测试')
    parser.add_argument('--test', type=str, help='要运行的测试函数名')
    parser.add_argument('--real', action='store_true', help='使用真实调用而不是录制的响应')
    parser.add_argument('--api-key', type=str, help='API Key')
    return parser.parse_args()

def get_vcr(scenario: str, use_real: bool = False):
    """获取指定场景的 VCR
    Args:
        scenario: 场景名称
        use_real: 是否使用真实调用（默认使用录制的响应）
    """
    return vcr.VCR(
        cassette_library_dir=str(FIXTURE_DIR),
        record_mode="all" if use_real else "none",  # 默认使用录制的响应
        match_on=['method', 'scheme', 'host', 'port', 'path', 'query', 'body'],
        filter_headers=['authorization'],
    )

@pytest.fixture
async def chat():
    """创建 ChatQwen 实例"""
    chat = ChatQwen(
        model="qwen-test",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        service_name="test_chat_qwen"
    )
    await chat.start_async()
    yield chat
    await chat.stop_async()

@pytest.mark.asyncio
async def test_normal_chat(chat, use_real=False):
    """测试正常对话场景"""
    with get_vcr("normal_chat", use_real).use_cassette("normal_response.yaml") as cass:
        messages = [{"role": "user", "content": "你好"}]
        blocks = []
        async for block in chat(messages):
            blocks.append(block)
            print(f"Received block: {block}")
        
        print(f"Using {'real' if use_real else 'recorded'} response")
        assert len(blocks) > 0
        assert blocks[-1].block_type == "usage"

@pytest.mark.asyncio
async def test_invalid_token(chat, use_real=False):
    """测试 Token 无效场景"""
    chat.model_args["api_key"] = "invalid_key"
    with get_vcr("invalid_token", use_real).use_cassette("invalid_token.yaml"):
        messages = [{"role": "user", "content": "你好"}]
        blocks = []
        async for block in chat(messages):
            blocks.append(block)
        
        assert blocks[0].block_type == "error"

if __name__ == "__main__":
    import asyncio
    args = parse_args()
    
    async def run_tests():
        chat = ChatQwen(
            api_key=args.api_key or os.getenv("DASHSCOPE_API_KEY"),
            service_name="test_chat_qwen"
        )
        await chat.start_async()
        
        try:
            if args.test:
                # 运行指定的测试
                test_func = globals().get(args.test)
                if test_func:
                    print(f"\nRunning test: {args.test}")
                    await test_func(chat, use_real=args.real)
                else:
                    print(f"Test {args.test} not found")
            else:
                # 运行所有测试
                print("\nRunning all tests...")
                await test_normal_chat(chat, use_real=args.real)
                await test_invalid_token(chat, use_real=args.real)
                
        finally:
            await chat.stop_async()
    
    asyncio.run(run_tests()) 