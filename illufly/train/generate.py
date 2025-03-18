import os
import json
import re
import random
import asyncio
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from collections import defaultdict
import traceback

from ..community import ChatOpenAI
from ..community.models import BlockType
from ..prompt import PromptTemplate
from .analyze import analyze_data

class GenerateData:
    """构造用于训练的数据"""
    
    def __init__(
        self, 
        output_dir: str = "data",
        model: str = "gpt-4o-mini",
        imitator: Optional[str] = None,
        batch_size: int = 5,
        temperature: float = 0.7
    ):
        self.output_dir = output_dir
        self.batch_size = batch_size
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 初始化LLM客户端
        self.llm = ChatOpenAI(
            model=model,
            imitator=imitator
        )
        self.temperature = temperature
        
    async def generate_batch(
        self,
        system_prompt: str,
        user_prompt: str,
        batch_id: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一批训练数据
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词，必须要求以JSON列表返回
            batch_id: 批次ID
            metadata: 可选的元数据，将添加到每个生成的数据项
            
        Returns:
            解析后的数据列表
        """
        # 调用LLM生成数据
        json_text = ""
        try:
            async for x in self.llm.generate(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature
            ):
                if x.block_type == BlockType.TEXT_FINAL:
                    json_text = x.text
                elif x.block_type == BlockType.TEXT_CHUNK:
                    print(x.text, end="")
                else:
                    # 如果API返回不是预期的结构，直接使用返回内容
                    json_text = str(x)
        except Exception as e:
            print(f"生成数据时出错: {e}")
            traceback.print_exc()
            return []
        
        # 解析响应JSON
        return self._parse_json_response(json_text, batch_id, metadata)
    
    def _parse_json_response(
        self,
        text: str,
        batch_id: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """解析JSON响应，增强错误处理"""
        if not text:
            print("生成的文本为空")
            return []
        
        try:
            # 查找JSON内容 - 尝试几种常见的包裹方式
            json_pattern = r'```(?:json)?(.*?)```|(\[.*\])'
            matches = re.findall(json_pattern, text, re.DOTALL)
            
            if matches:
                # 使用第一个匹配项
                for match in matches:
                    # 可能有多个捕获组，选择非空的那个
                    json_text = next((m.strip() for m in match if m.strip()), None)
                    if json_text:
                        break
                    else:
                        # 没找到格式化的JSON块，尝试解析整个文本
                        json_text = text
            
            # 尝试直接解析
            try:
                data = json.loads(json_text)
            except json.JSONDecodeError:
                # 尝试修复常见JSON错误
                cleaned_text = json_text.replace('""', '"')
                cleaned_text = re.sub(r',\s*\]', ']', cleaned_text)
                cleaned_text = re.sub(r',\s*\}', '}', cleaned_text)
                # 尝试去除非ASCII字符
                cleaned_text = re.sub(r'[^\x00-\x7F]+', ' ', cleaned_text)
                
                try:
                    data = json.loads(cleaned_text)
                except json.JSONDecodeError:
                    # 再尝试提取可能的JSON部分
                    json_obj_match = re.search(r'\[\s*\{.*\}\s*\]', cleaned_text, re.DOTALL)
                    if json_obj_match:
                        try:
                            data = json.loads(json_obj_match.group(0))
                        except:
                            print("JSON解析失败，所有尝试均未成功")
                            return []
                    else:
                        print("未找到有效的JSON结构")
                        return []
            
            # 确保数据是列表格式
            if not isinstance(data, list):
                if isinstance(data, dict):
                    # 如果是字典，查找可能包含数据的字段
                    for key in ['samples', 'data', 'results', 'items']:
                        if key in data and isinstance(data[key], list):
                            data = data[key]
                            break
                    else:
                        # 如果没找到列表字段，将字典放入列表
                        data = [data]
                else:
                    # 其他类型，强制转为列表
                    data = [data]
            
            # 添加元数据
            timestamp = datetime.now().isoformat()
            for item in data:
                if not isinstance(item, dict):
                    continue
                
                item['batch_id'] = batch_id
                item['timestamp'] = timestamp
                
                # 添加自定义元数据
                if metadata:
                    for key, value in metadata.items():
                        item[key] = value

            return data
            
        except Exception as e:
            print(f"处理JSON响应时出错: {e}")
            traceback.print_exc()
            return []
    
    async def generate_all_data(
        self,
        system_prompt: Union[str, PromptTemplate],
        user_prompt_template: Union[str, PromptTemplate], 
        num_batches: int, 
        batch_metadata: Optional[List[Dict[str, Any]]] = None,
        metadata_fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        生成所有批次的数据
        
        Args:
            system_prompt: 系统提示词
            user_prompt_template: 用户提示词模板，可以包含{{key}}格式的变量
            num_batches: 批次数量
            batch_metadata: 每个批次的元数据列表，如果提供，长度应与num_batches相同
            metadata_fields: 要视为元数据的字段(用于分组分析)
            
        Returns:
            所有生成的数据列表
        """
        all_data = []
        
        # 使用时间戳生成唯一输出文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(self.output_dir, f"data_{timestamp}.json")
        
        print(f"开始生成数据，将保存到: {output_file}")
        
        for i in range(num_batches):
            # 构建变量映射，默认包含批次号和批次大小
            variables = {
                "batch_id": i+1,
                "count": self.batch_size,
            }
            
            # 添加批次元数据
            metadata = None
            if batch_metadata and i < len(batch_metadata):
                metadata = batch_metadata[i]
                # 同时将元数据合并到模板变量中
                if metadata:
                    variables.update(metadata)

            system_prompt = system_prompt if isinstance(system_prompt, str) else system_prompt.format(variables)
            user_prompt_template = user_prompt_template if isinstance(user_prompt_template, str) else user_prompt_template.format(variables)

            print(f"\n===== 生成批次 {i+1}/{num_batches} =====")
            batch_data = await self.generate_batch(
                system_prompt, 
                user_prompt_template,
                i+1,
                metadata
            )
            
            if batch_data:
                all_data.extend(batch_data)
                print(f"批次 {i+1} 完成: 获取到 {len(batch_data)} 条数据")
                
                # 每批次后保存当前所有数据
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=2)
                print(f"已更新数据文件，当前共 {len(all_data)} 条数据")
            else:
                print(f"批次 {i+1} 未生成有效数据")
                
                # 添加延迟以避免API限制
            if i < num_batches - 1:  # 最后一批不需要等待
                await asyncio.sleep(1)
        
        print(f"\n数据生成完成，共 {len(all_data)} 条数据，已保存到: {output_file}")
        
        # 分析数据并打印报告
        if all_data:
            report = analyze_data(
                all_data, 
                max_categories=5,  # 每个类别最多显示5个值 
                metadata_fields=metadata_fields  # 传入元数据字段列表
            )
            print("\n===== 数据分析报告 =====")
            print(report)
            
            # 保存分析报告
            report_file = os.path.join(self.output_dir, f"data_report_{timestamp}.txt")
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"分析报告已保存到: {report_file}")
        
        return all_data
