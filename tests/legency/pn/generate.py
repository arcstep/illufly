from illufly.train import GenerateData
from illufly.prompt import PromptTemplate
import asyncio

system_prompt = """
你是一个帮助生成策略网络训练数据的助手。你需要生成用户查询样本及其对应的动作分类。

对于每个用户查询，你需要确定最合适的处理方式：
1. 直接对话：适用于无需额外查询的一般性问题，如闲聊、意见请求等
2. 查询知识库：适用于需要事实性知识的问题，如"什么是量子力学"、"北京有哪些景点"等
3. 查询数据库：适用于需要特定用户或系统数据的问题，如"我的账户余额是多少"、"订单12345的状态"等

对于数据库查询，还需要生成一个合理的SQL查询语句。
"""

user_prompt_template = PromptTemplate(text="""
请针对{{domain}}领域，生成{{count}}个多样化的用户问题样本。

对于每个样本，请提供以下信息：
1. 用户查询：实际用户可能提出的问题
2. 动作类型：0(直接对话)、1(查询知识库)或2(查询数据库)
3. 动作参数：对于查询知识库，提供检索关键词；对于查询数据库，提供生成SQL的关键信息
4. 解释：简短说明为何选择此动作类型

请以JSON格式输出，确保格式正确且内容多样化，覆盖各种复杂度的查询。
动作类型的分布应大致平衡，但允许适当变化。

输出示例（请直接输出使用 ```json ```包裹的JSON格式，不要评论，不要其他内容）:

```json
[
    {
        "用户查询": "我的账户余额是多少？",
        "动作类型": 2,
        "动作参数": {'查询内容': '当前用户帐户余额'},
        "解释": "用户想要查询特定账户的余额信息，适合使用数据库查询来获取用户的具体数据。"
    },
    ...
]
```
""")

async def main():
    generator = GenerateData(output_dir="./data")

    batch_metadata = [
        {"domain": "售前咨询"},
        {"domain": "Linux运维"}
    ]

    # 生成数据
    await generator.generate_all_data(
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        num_batches=2,
        batch_metadata=batch_metadata
    )

if __name__ == "__main__":
    asyncio.run(main())
