import pytest
import vcr
import os
import json
import logging
from pathlib import Path
from illufly.llm.chat_openai import ChatOpenAI

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 设置录制文件存储路径
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "chat_openai"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

def get_vcr(scenario: str, use_real: bool = False):
    """获取指定场景的 VCR"""
    return vcr.VCR(
        cassette_library_dir=str(FIXTURE_DIR),
        record_mode="all" if use_real else "none",
        match_on=['method', 'scheme', 'host', 'port', 'path', 'query', 'body'],
        filter_headers=['authorization'],
        custom_patches=((
            'httpx.AsyncClient.send',
            'tests.llm.vcr_patches.async_send',
            'tests.llm.vcr_patches.AsyncClientSendWrapper'
        ),)
    )

@pytest.fixture(autouse=True)
def setup_logging(caplog):
    """设置日志级别"""
    caplog.set_level(logging.DEBUG)

@pytest.fixture
async def chat():
    """异步 fixture"""
    chat = ChatOpenAI(
        prefix="QWEN",
        model="qwen-test",
        service_name="test_chat_openai",
        logger=logger
    )
    await chat.start_async()
    try:
        yield chat
    finally:
        await chat.stop_async()

@pytest.fixture
def chat_cleanup(chat):
    """处理清理的 fixture"""
    try:
        yield chat
    finally:
        chat.stop()

@pytest.mark.asyncio
async def test_normal_chat(chat, use_real):
    """测试正常对话场景"""
    with get_vcr("normal_chat", use_real).use_cassette("normal_response.yaml"):
        messages = [{"role": "user", "content": "你好"}]
        blocks = []
        async for block in chat(messages):  # 直接使用 chat 实例
            blocks.append(block)
            print(f"Received block: {block}")
        
        print(f"Using {'real' if use_real else 'recorded'} response")
        
        assert len(blocks) >= 2
        assert any(block.block_type == "usage" for block in blocks)
        assert blocks[-1].block_type == "end"

@pytest.mark.asyncio
async def test_invalid_message_format(chat):
    """测试无效的消息格式"""
    invalid_messages = [
        "不是字典的消息",  # 不是字典
        {"missing_role": "content"},  # 缺少必要的键
        {"role": 123, "content": "内容"},  # role 不是字符串
        {"role": "user", "content": 456}  # content 不是字符串
    ]
    
    for msg in invalid_messages:
        with pytest.raises(ValueError) as exc_info:
            async for _ in chat([msg]):
                pass
        print(f"Expected error raised: {str(exc_info.value)}")

@pytest.mark.asyncio
async def test_invalid_token(chat, use_real):
    """测试 Token 无效场景"""
    chat.model_args["api_key"] = "invalid_key"
    with get_vcr("invalid_token", use_real).use_cassette("invalid_token.yaml"):
        messages = [{"role": "user", "content": "你好"}]
        blocks = []
        async for block in chat(messages):
            blocks.append(block)
        
        assert any(block.block_type == "error" for block in blocks)

if __name__ == "__main__":
    import asyncio
    args = parse_args()
    
    async def run_tests():
        chat = ChatOpenAI(
            prefix="QWEN",
            model="qwen-test",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            service_name="test_chat_openai",
            logger=logger
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