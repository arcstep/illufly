#!/usr/bin/env python3
"""
带错误捕获的命令行入口
"""
import sys
import traceback

def main():
    """带详细错误处理的入口点"""
    try:
        print("===CLI启动===")
        # 显示调试信息
        import platform
        print(f"Python版本: {sys.version}")
        print(f"平台: {platform.platform()}")
        print(f"命令行参数: {sys.argv}")
        
        # 先导入click验证是否能正常工作
        import click
        print("click导入成功")
        
        # 然后尝试导入主模块
        from illufly.__main__ import main as real_main
        print("__main__.main导入成功")
        
        # 执行主函数
        return real_main()
        
    except Exception as e:
        print("\n===错误详情===")
        print(f"错误类型: {type(e)}")
        print(f"错误信息: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())