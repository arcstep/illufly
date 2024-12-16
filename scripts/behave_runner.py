# scripts/behave_runner.py
import argparse
import subprocess
import sys
import os

def run_bdd(feature=None, tags=None):
    """运行 BDD 测试
    
    Args:
        feature: 可选,指定要运行的特性名称(不含路径和扩展名)
        tags: 可选,指定要运行的标签
        
    Examples:
        >>> run_bdd()  # 运行所有测试
        >>> run_bdd(feature="register")  # 运行注册相关的特性
        >>> run_bdd(tags="@wip")  # 运行带 @wip 标签的场景
        >>> run_bdd(tags="@core,@validation")  # 运行带多个标签的场景
        >>> run_bdd(feature="register", tags="@validation")  # 运行注册特性中的验证场景
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    features_dir = "bdd/features"
    
    cmd_parts = ["behave", "-v", "-k", "--format=pretty"]
    
    # 构建标签表达式
    tag_expr = []
    if feature:
        # 确保添加 @ 前缀
        feature_tag = f"@{feature}" if not feature.startswith("@") else feature
        tag_expr.append(feature_tag)
    if tags:
        # 确保添加 @ 前缀
        if not tags.startswith("@"):
            tags = "@" + tags.replace(",", ",@")
        tag_expr.append(tags)
    
    if tag_expr:
        # 使用 -t 参数,不需要引号
        cmd_parts.append(f"-t {','.join(tag_expr)}")
    
    cmd_parts.append(features_dir)
    
    cmd = " ".join(cmd_parts)
    print(f"执行命令: {cmd}")
    print(f"Features目录: {features_dir}")
    
    result = subprocess.run(cmd_parts, capture_output=False)
    if result.returncode != 0:
        print(f"测试执行失败: {result}")
        sys.exit(1)

def main():
    """命令行入口函数
    
    支持以下使用方式:
    
    1. 运行 WIP 场景:
        poetry run bdd --wip
    
    2. 运行指定标签的场景:
        poetry run bdd --tags=@core
        poetry run bdd --tags=@validation
        poetry run bdd --tags=@core,@validation
    
    3. 运行指定特性:
        poetry run bdd --feature register
    """
    parser = argparse.ArgumentParser(description="运行 BDD 测试")
    parser.add_argument("--wip", action="store_true", help="只运行 @wip 标记的场景")
    parser.add_argument("--feature", help="指定要运行的特性名称")
    parser.add_argument("--tags", help="指定要运行的标签表达式")
    args = parser.parse_args()
    
    if args.wip:
        run_bdd(tags="@wip")
    else:
        run_bdd(feature=args.feature, tags=args.tags)

if __name__ == "__main__":
    main()