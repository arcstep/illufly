import asyncio
import json
import logging
import os
import re
from typing import Any, List, Dict

import openai
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load environment variables
load_dotenv()

class AdvancedWeatherMCPClient:
    """使用MCP工具、资源和提示语的高级天气客户端"""
    
    def __init__(self):
        """初始化客户端"""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        if not self.api_key:
            raise ValueError("没有找到OPENAI_API_KEY环境变量")
            
        self.openai_client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        
        # MCP服务器参数配置
        self.server_params = StdioServerParameters(
            command="python",  # 使用Python解释器
            args=["weather_server.py"],  # 执行天气服务器脚本
        )
        
        # 保存可用资源和提示语
        self.available_tools = []
        self.available_resources = []
        self.available_prompts = []
    
    # 工具结果解析功能
    def extract_tool_result(self, tool_result):
        """从MCP工具结果中提取文本内容"""
        try:
            # 处理 CallToolResult 对象
            if hasattr(tool_result, 'content') and isinstance(tool_result.content, list) and len(tool_result.content) > 0:
                content_item = tool_result.content[0]
                if hasattr(content_item, 'text'):
                    return content_item.text
                return str(content_item)
            elif hasattr(tool_result, 'text'):
                return tool_result.text
            elif hasattr(tool_result, 'result'):
                return tool_result.result
            else:
                return str(tool_result)
        except Exception as e:
            logging.warning(f"提取工具结果时出错: {e}")
            return str(tool_result)
    
    async def read_resource(self, session, uri):
        """读取MCP资源"""
        try:
            content, mime_type = await session.read_resource(uri)
            logging.info(f"读取资源 {uri}, MIME类型: {mime_type}")
            return content
        except Exception as e:
            logging.error(f"读取资源失败 {uri}: {e}")
            return None
    
    async def get_prompt(self, session, prompt_name, arguments=None):
        """获取MCP提示语"""
        try:
            prompt_result = await session.get_prompt(prompt_name, arguments or {})
            
            # 添加详细日志
            logging.info(f"提示语结果类型: {type(prompt_result)}")
            logging.info(f"提示语结果属性: {dir(prompt_result)}")
            
            # 正确处理不同格式的提示语结果
            if hasattr(prompt_result, 'description'):
                logging.info(f"提示语描述: {prompt_result.description}")
            
            if hasattr(prompt_result, 'messages') and prompt_result.messages:
                # 如果是消息列表，转换为OpenAI可用格式
                openai_messages = []
                for msg in prompt_result.messages:
                    if hasattr(msg, 'role') and hasattr(msg, 'content'):
                        openai_messages.append({
                            "role": msg.role, 
                            "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
                        })
                return openai_messages
            elif hasattr(prompt_result, 'text'):
                return prompt_result.text
            else:
                return str(prompt_result)
        except Exception as e:
            logging.error(f"获取提示语失败 {prompt_name}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None
    
    async def start_chat(self):
        """启动与用户的聊天会话"""
        # 连接到MCP服务器
        async with stdio_client(self.server_params) as (read, write):
            # 创建MCP会话
            async with ClientSession(read, write) as session:
                # 初始化连接
                await session.initialize()
                
                # 加载所有可用工具、资源和提示语
                await self.load_mcp_capabilities(session)
                
                # 创建系统消息
                system_message = """你是一个气象助手，可以提供全球各地的天气信息。
当用户询问天气时，使用get_weather工具获取数据。
你还可以提供历史天气数据和详细的天气报告。
提供友好、信息丰富的回复，并在合适的情况下给出建议。"""
                
                # 初始化聊天历史
                messages = [{"role": "system", "content": system_message}]
                
                print("\n欢迎使用高级天气助手！输入'退出'结束对话。")
                print("可用命令:")
                print("  '历史天气 [城市]' - 查询城市历史天气数据")
                print("  '天气报告 [城市]' - 获取城市详细天气报告")
                print("  '[城市] 天气' - 查询当前天气\n")
                
                # 聊天循环
                while True:
                    try:
                        # 获取用户输入
                        user_input = input("您: ").strip()
                        if user_input.lower() in ["exit", "quit", "退出"]:
                            print("再见！")
                            break
                        
                        # 检查是否是资源请求 - 历史天气
                        if "历史天气" in user_input:
                            if not self.available_resources:
                                print("\n助手: 抱歉，目前没有可用的天气历史数据资源。")
                                continue
                            
                            city_match = re.search(r'历史天气\s+([^\s]+)', user_input)
                            if city_match:
                                city = city_match.group(1)
                                print(f"\n助手: 正在查询{city}的历史天气数据...")
                                history_data = await self.read_resource(session, f"weather://{city}/history")
                                if history_data:
                                    print(f"\n助手: {history_data}")
                                    continue
                        
                        # 检查是否是提示语请求 - 天气报告
                        if "天气报告" in user_input:
                            city_match = re.search(r'天气报告\s+([^\s]+)', user_input)
                            if city_match:
                                city = city_match.group(1)
                                print(f"\n助手: 正在准备{city}的详细天气报告...")
                                
                                try:
                                    prompt_result = await self.get_prompt(session, "weather_report", {"city": city})
                                    
                                    if prompt_result:
                                        # 方法1: 将提示语内容作为用户消息的一部分
                                        user_message = f"请为{city}提供天气报告，基于以下指南:\n\n{prompt_result}"
                                        
                                        # 使用普通消息处理流程
                                        current_messages = messages.copy()
                                        current_messages.append({"role": "user", "content": user_message})
                                        
                                        # 处理请求
                                        await self.process_with_tools(current_messages, session)
                                        continue
                                except Exception as e:
                                    logging.error(f"处理提示语出错: {e}")
                                    print(f"\n系统错误: 无法处理天气报告请求。请重试。")
                        
                        # 添加用户消息到历史
                        messages.append({"role": "user", "content": user_input})
                        
                        # 使用常规工具处理流程
                        await self.process_with_tools(messages, session)
                        
                    except Exception as e:
                        logging.error(f"对话循环异常: {str(e)}")
                        import traceback
                        logging.error(traceback.format_exc())
                        print(f"\n系统错误: {str(e)}\n请重试或联系管理员。")
    
    async def load_mcp_capabilities(self, session):
        """加载所有MCP功能"""
        # 获取可用工具
        tools_response = await session.list_tools()
        self.available_tools = []
        
        for item in tools_response:
            if item[0] == "tools":
                for tool in item[1]:
                    schema = tool.inputSchema.copy()
                    if "type" not in schema:
                        schema["type"] = "object"
                    self.available_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": schema
                        }
                    })
        
        logging.info(f"可用工具: {[t['function']['name'] for t in self.available_tools]}")
        
        # 获取可用资源
        resources_response = await session.list_resources()
        self.available_resources = []
        
        for item in resources_response:
            if item[0] == "resources":
                for resource in item[1]:
                    self.available_resources.append({
                        "name": resource.name,
                        "description": resource.description,
                        "uri_template": resource.uri_template
                    })
        
        logging.info(f"可用资源: {[r['uri_template'] for r in self.available_resources]}")
        
        # 获取可用提示语
        prompts_response = await session.list_prompts()
        self.available_prompts = []
        
        for item in prompts_response:
            if item[0] == "prompts":
                for prompt in item[1]:
                    self.available_prompts.append({
                        "name": prompt.name,
                        "description": prompt.description
                    })
        
        logging.info(f"可用提示语: {[p['name'] for p in self.available_prompts]}")
    
    async def process_with_tools(self, messages, session):
        """处理需要工具调用的对话流程"""
        # 调用OpenAI API获取响应
        logging.info("发送请求到OpenAI API...")
        response = self.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=self.available_tools,
            tool_choice="auto",
            temperature=0.7,
        )
        
        assistant_message = response.choices[0].message
        
        # 检查是否有工具调用
        if hasattr(assistant_message, 'tool_calls') and assistant_message.tool_calls:
            # 将助手消息添加到历史中（包含工具调用）
            messages.append({
                "role": "assistant",
                "content": assistant_message.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in assistant_message.tool_calls
                ]
            })
            
            # 处理工具调用并收集结果
            tool_responses = []
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    function_args = {}
                    logging.warning(f"无法解析工具参数: {tool_call.function.arguments}")
                
                logging.info(f"调用工具: {function_name} 参数: {function_args}")
                
                try:
                    # 使用MCP会话调用工具
                    tool_result = await session.call_tool(function_name, function_args)
                    
                    # 提取工具结果
                    result_content = self.extract_tool_result(tool_result)
                    
                    # 添加日志以便调试
                    logging.info(f"工具返回类型: {type(tool_result)}")
                    logging.info(f"提取的工具结果: {result_content}")
                    
                    # 将工具结果添加到消息历史
                    tool_response = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": result_content
                    }
                    messages.append(tool_response)
                    tool_responses.append(tool_response)
                except Exception as e:
                    error_msg = f"工具调用失败 {function_name}: {str(e)}"
                    logging.error(error_msg)
                    # 添加错误结果
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": f"错误: {error_msg}"
                    })
            
            # 显示工具调用
            print("\n助手: 正在处理数据...")
            
            # 使用工具结果获取最终回复
            try:
                logging.info("发送工具结果到OpenAI API...")
                
                second_response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.7,
                )
                
                final_response = second_response.choices[0].message.content
                messages.append({"role": "assistant", "content": final_response})
                print(f"\n助手: {final_response}")
            except Exception as e:
                # 如果第二次API调用失败，则使用简化回复
                logging.error(f"获取最终回复失败: {str(e)}")
                tool_results_text = "\n".join([m["content"] for m in tool_responses])
                fallback_response = f"根据查询，{tool_results_text}\n\n(系统自动生成的简化回复)"
                print(f"\n助手: {fallback_response}")
                messages.append({"role": "assistant", "content": fallback_response})
        else:
            # 没有工具调用，直接显示助手回复
            messages.append({"role": "assistant", "content": assistant_message.content})
            print(f"\n助手: {assistant_message.content}")


async def main() -> None:
    """Initialize and run the chat session."""
    try:        
        client = AdvancedWeatherMCPClient()
        await client.start_chat()
    except Exception as e:
        logging.error(f"主程序异常: {e}")
        import traceback
        logging.error(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())