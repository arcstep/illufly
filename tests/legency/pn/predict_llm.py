from illufly.train import GenerateData
from illufly.prompt import PromptTemplate
from illufly.community import ChatOpenAI
from illufly.community.models import BlockType
import asyncio
import json
import argparse

system_prompt = """
请你根据用户问题预测用户意图，然后输出意图对应的动作类型的序号。
其中动作类型包括：
0 直接对话：适用于无需额外查询的一般性问题，如闲聊、意见请求等
1 查询知识库：适用于需要事实性知识的问题，如"什么是量子力学"、"北京有哪些景点"等
2 查询数据库：适用于需要特定用户或系统数据的问题，如"我的账户余额是多少"、"订单12345的状态"等

输入示例：
```
用户问题：
我的账户余额是多少？
```

输出示例：
```json
{
    "动作类型": 1,
    "解释": "用户想要查询特定账户的余额信息，适合使用数据库查询来获取用户的具体数据。"
}
```
"""

user_prompt_template = PromptTemplate(text="""
用户问题：
{{question}}
""")

async def main():
    parser = argparse.ArgumentParser(description="使用大模型预测用户意图")
    parser.add_argument("path", help="要预测的文件或目录路径")
    args = parser.parse_args()

    llm = ChatOpenAI(
        model="qwen-plus",
        imitator="QWEN"
    )

    print(f"预测文件: {args.path}")
    data = json.load(open(args.path))
    results = []
    for item in data:
        question = item["用户查询"]
        json_data = ""
        print(f"预测问题: {question}")
        print(f"正确类型: {item['动作类型']}")
        async for x in llm.generate(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_template.format({"question": question})}
            ],
            temperature=0.0
        ):
            if x.block_type == BlockType.TEXT_FINAL:
                json_data = x.text
            elif x.block_type == BlockType.TEXT_CHUNK:
                print(x.text, end="")
        json_data = json_data.strip().replace("```json", "").replace("```", "")
        result = json.loads(json_data)

        results.append({
            "用户查询": question,
            "真实动作类型": item["动作类型"],
            "预测动作类型": result["动作类型"],
            "预测解释": result["解释"]
        })

    json.dump(results, open(f"{args.path}_llm_predict.json", "w"), indent=4, ensure_ascii=False)

    correct_count = sum(1 for result in results if result["真实动作类型"] == result["预测动作类型"])
    wrong_count = len(results) - correct_count
    correct_rate = correct_count / len(results) * 100
    print(f"""
    预测结果已保存到 {args.path}_llm_predict.json
    其中：
    正确预测数：{correct_count}
    错误预测数：{wrong_count}
    正确率：{correct_rate:.2f}%
    """)

if __name__ == "__main__":
    asyncio.run(main())
