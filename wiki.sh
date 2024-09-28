#!/bin/bash

# 获取过滤名称（如果有）
filter_name="$1"

# 创建目标目录
mkdir -p ./wiki/__md__

# 函数处理 Markdown 文件内容
process_markdown_file() {
    local file="$1"
    awk '
    BEGIN {
        in_code_block = 0;
        blank = 0;
    }
    function ansi_to_sh(s) {
        gsub(/\x1b\[[0-9;]*m/, "", s);
        return s;
    }
    {
        if ($0 ~ /^```python/) {
            in_code_block = 1;
            code_block_content = "";
            next;
        }
        if ($0 ~ /^```/ && in_code_block) {
            if (code_block_content != "") {
                print "```python";
                print code_block_content;
                print "```";
            }
            in_code_block = 0;
            next;
        }
        if (in_code_block) {
            code_block_content = code_block_content $0 "\n";
            next;
        }
        if ($0 ~ /\x1b\[[0-9;]*m/) {
            print ansi_to_sh($0);
            next;
        }
        if ($0 ~ /^$/) {
            blank++;
        } else {
            blank = 0;
        }
        if (blank <= 2) {
            print;
        }
    }
    ' "$file" > "${file}.tmp"

    mv "${file}.tmp" "$file"
}

# 查找并转换所有 Jupyter Notebook 文件，排除隐藏文件和目录
find ./wiki -name "*.ipynb" ! -path "*/.*/*" | while read notebook; do
    # 获取文件名和目录
    filename=$(basename "$notebook" .ipynb)
    
    # 检查文件名是否包含过滤名称（如果有）
    if [ -z "$filter_name" ] || [[ "$filename" == *"$filter_name"* ]]; then
        # 转换为 Markdown
        jupyter nbconvert --to markdown "$notebook" --output-dir=./wiki/__md__
        
        # 处理 Markdown 文件
        markdown_file="./wiki/__md__/$filename.md"
        echo "检查文件: $markdown_file"
        process_markdown_file "$markdown_file"
    fi
done