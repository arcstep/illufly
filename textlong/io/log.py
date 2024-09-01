import json
from .json import merge_blocks_by_index

def stream_log(call, *args, **kwargs):
    """
    针对任何回调函数，只要符合规范的返回TextBlock对象的生成器，就可以使用这个函数来
    打印流式日志。

    也可以将打印日志升级为提交到 redis 或消息队列中，实现跨系统的流信息交换，
    如 stream_redis / stream_mq 等。
    """

    output_text = ""
    tools_call = []
    last_block_type = ""

    for block in call(*args, **kwargs):
        if block.block_type in ['text', 'chunk', 'front_matter']:
            output_text += block.text
        
        if block.block_type in ['tools_call']:
            tools_call.append(json.loads(block.text))

        if block.block_type in ['chunk']:
            print(block.text_with_print_color, end="")
            last_block_type = block.block_type

        if block.block_type in ['info', 'warn', 'text']:
            if last_block_type == "chunk":
                print("\n")
                last_block_type = ""
            print(f'>-[{block.block_type.upper()}]>> {block.text_with_print_color}')
            last_block_type = block.block_type
    
    if last_block_type == "chunk":
        print("\n")
        last_block_type = ""
    
    final_tools_call = merge_blocks_by_index(tools_call)
    if final_tools_call:
        print(f'>-[TOOLS_CALL]>> {json.dumps(final_tools_call)}')

    return {"output": output_text, "tools_call": final_tools_call}

