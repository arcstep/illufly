#!/bin/bash

# 创建目标目录
mkdir -p ./wiki/__md__

# 指定要处理的文件名（不带扩展名）
target_files=("why" "another_file")

# 查找并转换所有 Jupyter Notebook 文件，排除隐藏文件和目录
find ./wiki -name "*.ipynb" ! -path "*/.*/*" | while read notebook; do
    # 获取文件名和目录
    filename=$(basename "$notebook" .ipynb)
    dir=$(dirname "$notebook")
    
    # 检查文件名是否在目标文件列表中
    if [[ " ${target_files[@]} " =~ " ${filename} " ]]; then
        # 转换为 Markdown
        jupyter nbconvert --to markdown "$notebook" --output-dir=./wiki/__md__
        
        # 查找并转换带有 ANSI 颜色码的文件
        markdown_file="./wiki/__md__/$filename.md"
        if grep -q $'\e' "$markdown_file"; then
            # 确保 ansi2html 可用
            if command -v ansi2html > /dev/null; then
                ansi2html < "$markdown_file" > "${markdown_file%.md}.html"
                mv "${markdown_file%.md}.html" "$markdown_file"
                
                # 去除包含 <span> 的行首空格
                awk '/<span/ {gsub(/^[[:space:]]+/, ""); print} !/<span/ {print}' "$markdown_file" > temp && mv temp "$markdown_file"
            else
                echo "ansi2html 未找到，请安装它。"
                exit 1
            fi
        fi
    fi
done
