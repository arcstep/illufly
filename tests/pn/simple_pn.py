from illufly.memory.pn import PolicyNetwork, PolicyAgent, LLMInterface
from illufly.rocksdb import IndexedRocksDB
from illufly.community.openai import OpenAIEmbeddings
import asyncio
import sys

MODEL_PATH = "./tests/pn/models"

# 统一日志队列初始化
import logging
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
log_queue = Queue()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# 异步日志处理器
queue_handler = QueueHandler(log_queue)
logger.addHandler(queue_handler)

# 输出处理器配置
handlers = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler("pn_async.log", mode='a', encoding='utf-8')
]

# 启动监听器
listener = QueueListener(log_queue, *handlers)
listener.start()

# 使用示例
async def main():
    # 优先初始化数据库连接
    db_path = "./tests/pn/embeddings"
    rocks_db = IndexedRocksDB(db_path)
    
    # 初始化嵌入模型
    embeddings = OpenAIEmbeddings(
        model="text-embedding-ada-002",
        imitator="OPENAI",
        dim=1536,
        db=rocks_db  # 使用已初始化的数据库实例
    )
    
    # 策略网络初始化
    policy_network = PolicyNetwork(
        confidence_threshold=0.7,
        model_path=MODEL_PATH,
        embeddings=embeddings
    )
    
    # 在初始化后添加测试日志
    logger.debug("策略网络初始化完成，动作空间: %s", policy_network.action_names)
    
    # 在加载模型后添加检查
    if policy_network.model_path:
        logger.debug("已加载模型路径: %s", policy_network.model_path)
    else:
        logger.debug("未加载预训练模型")
    
    # 初始化大模型接口
    llm = LLMInterface()
    
    # 创建策略代理
    agent = PolicyAgent(policy_network, llm, confidence_threshold=0.7)
    
    # 处理用户查询示例
    queries = [
        "我怎么修改文件权限？",
        "有什么产品套餐",
        "解释一下量子力学的基本原理"
    ]
    
    for query in queries:
        print(f"\n处理查询: {query}")
        result = await agent.process_query(query)
        print(f"决策: {result['action_name']}")
        print(f"来源: {result['source']}")
        print(f"执行结果: {agent.execute_action(result)}")
    
    # 添加新动作示例
    # policy_network.add_action("调用外部API")
    
    # 月度更新示例
    await agent.monthly_update()

if __name__ == "__main__":
    asyncio.run(main())