from illufly.train import GenerateData
from illufly.prompt import PromptTemplate
import asyncio

async def main():
    generator = GenerateData(output_dir="./data")

    system_prompt = """
    你是一个帮助生成数据的助手。请按照用户要求生成数据样本，并以JSON格式返回。
    """

    user_prompt_template = PromptTemplate(text="""
    请生成{{count}}个关于{{domain}}的数据样本。

    每个样本应包含以下字段：
    - title: 标题
    - content: 内容
    - tags: 标签列表

    请以JSON列表格式返回结果。
    """)

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
