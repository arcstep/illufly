import json
import sys
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP, Context

# 创建MCP服务器
mcp = FastMCP("Weather Service")

# 添加天气工具
@mcp.tool()
def get_weather(city: str, date: str = "today") -> str:
    """获取指定城市的天气信息
    
    Args:
        city: 城市名称
        date: 日期，默认为今天
        
    Returns:
        天气信息描述
    """
    # 添加调试日志
    print(f"工具被调用: city={city}, date={date}")
    
    # 模拟天气数据（实际应用中会调用真实API）
    weather_data = {
        "beijing": {"today": "晴天, 25°C", "tomorrow": "多云, 23°C"},
        "shanghai": {"today": "多云, 28°C", "tomorrow": "小雨, 26°C"},
        "guangzhou": {"today": "雨, 30°C", "tomorrow": "暴雨, 29°C"},
        "new york": {"today": "晴天, 22°C", "tomorrow": "晴天, 24°C"},
        "london": {"today": "多云, 18°C", "tomorrow": "小雨, 17°C"}
    }
    
    city = city.lower()
    print(f"查找城市: {city}")
    print(f"可用城市: {list(weather_data.keys())}")
    
    if city not in weather_data:
        result = f"抱歉，没有找到{city}的天气信息。"
        print(f"返回结果: {result}")
        return result
    
    if date not in weather_data[city]:
        result = f"只能查询今天(today)或明天(tomorrow)的天气。"
        print(f"返回结果: {result}")
        return result
    
    result = f"{city.title()}的{date}天气: {weather_data[city][date]}"
    print(f"返回结果: {result}")
    return result

# 添加天气历史资源
@mcp.resource("weather://{city}/history")
def get_weather_history(city: str) -> str:
    """获取城市的历史天气数据
    
    Args:
        city: 城市名称
        
    Returns:
        历史天气数据
    """
    city = city.lower()
    history_data = {
        "beijing": "北京过去一周平均温度: 24°C, 最高: 29°C, 最低: 19°C",
        "shanghai": "上海过去一周平均温度: 27°C, 最高: 32°C, 最低: 22°C",
        "guangzhou": "广州过去一周平均温度: 30°C, 最高: 34°C, 最低: 25°C"
    }
    
    if city in history_data:
        return history_data[city]
    return f"没有找到{city}的历史天气数据。"

# 添加天气提示模板
@mcp.prompt()
def weather_report(city: str) -> str:
    """创建天气报告提示
    
    Args:
        city: 城市名称
        
    Returns:
        格式化的天气报告提示
    """
    return f"""请为{city}提供详细的天气分析报告，包括:
1. 今日天气概况
2. 温度范围与体感
3. 适合进行的户外活动
4. 穿衣建议

使用get_weather工具获取天气数据。
"""

if __name__ == "__main__":
    mcp.run()