# scripts/behave_runner.py
import argparse
import subprocess
import sys
import os

def run_bdd(feature=None, tags=None):
    """运行 BDD 测试
    
    支持以下运行模式：
    1. 不带参数：运行所有测试
    2. 指定特性：运行特定功能的测试
    3. 指定标签：运行带特定标签的测试
    4. 组合模式：同时指定特性和标签
    
    Args:
        feature (str, optional): 要运行的特性名称，无需包含路径和扩展名
        tags (str, optional): 要运行的标签表达式，多个标签用逗号分隔
        
    Examples:
        >>> run_bdd()  # 运行所有测试
        >>> run_bdd(feature="register")  # 运行注册相关的特性
        >>> run_bdd(tags="@wip")  # 运行标记为开发中的场景
        >>> run_bdd(tags="@core,@validation")  # 运行核心功能和验证相关的场景
        >>> run_bdd(feature="register", tags="@validation")  # 运行注册功能中的验证场景
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    features_dir = "tests_bdd/features"
    
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
    """BDD 测试运行器的命令行入口
    
    支持以下使用方式：
    1. 运行所有测试：
        poetry run bdd
    
    2. 运行开发中(WIP)的场景：
        poetry run bdd --wip
    
    3. 运行指定标签的场景：
        poetry run bdd --tags=@core
        poetry run bdd --tags=@validation
        poetry run bdd --tags=@core,@validation
    
    4. 运行指定特性：
        poetry run bdd --feature register
    
    5. 组合使用：
        poetry run bdd --feature register --tags=@validation
    
    参数说明：
        --wip: 只运行标记为 @wip 的场景
        --feature: 指定要运行的特性名称
        --tags: 指定要运行的标签表达式，多个标签用逗号分隔
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