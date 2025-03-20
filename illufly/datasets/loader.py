import os
import json
import pandas as pd
import urllib.request
import zipfile
import tarfile
import logging
from typing import Dict, List, Optional, Union, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NL2SQLDatasetLoader:
    """用于加载和处理NL2SQL数据集的工具类"""
    
    DATASET_CONFIGS = {
        # 中文数据集（可自动下载）
        "chase": {
            "url": "https://github.com/xjtu-intsoft/chase/archive/refs/heads/master.zip",
            "local_path": "data/chase/",
            "file_format": "json",
            "language": "zh"
        },
        "cspider": {
            "url": "https://github.com/taolusi/chisp/archive/refs/heads/master.zip",
            "local_path": "data/cspider/",
            "file_format": "json", 
            "language": "zh"
        },
        # 使用可自动下载的替代数据集
        "nl2sql-cn": {
            "url": "https://github.com/ZhuiyiTechnology/nl2sql_baseline/archive/refs/heads/master.zip",
            "local_path": "data/nl2sql-cn/",
            "file_format": "json",
            "language": "zh"
        },
        "tableqa-cn": {
            "url": "https://github.com/ZhuiyiTechnology/TableQA/archive/refs/heads/master.zip",
            "local_path": "data/tableqa-cn/",
            "file_format": "json",
            "language": "zh"
        },
        # 英文数据集（可自动下载）
        "wikisql": {
            "url": "https://github.com/salesforce/WikiSQL/archive/refs/heads/master.zip",
            "local_path": "data/wikisql/",
            "file_format": "json",
            "language": "en"
        },
        "spider-sqa": {  # Spider-SQA是可以自动下载的Spider变种
            "url": "https://github.com/taoyds/spider-sqa/archive/refs/heads/master.zip",
            "local_path": "data/spider-sqa/",
            "file_format": "json",
            "language": "en"
        },
        # 对话式NL2SQL数据集
        "cosql": {  # 多轮对话SQL数据集
            "url": "https://yale-lily.github.io/cosql/cosql_dataset.zip",  # 直接ZIP下载链接
            "local_path": "data/cosql/",
            "file_format": "json",
            "language": "en",
            "is_conversational": True
        },
        "sparc": {  # 上下文相关的跨域对话SQL数据集
            "url": "https://yale-lily.github.io/sparc/sparc_dataset.zip",  # 直接ZIP下载链接
            "local_path": "data/sparc/",
            "file_format": "json",
            "language": "en",
            "is_conversational": True
        },
        "squall": {  # 新数据集，包含自然语言问题和对应的SQL查询
            "url": "https://github.com/tzshi/squall/archive/refs/heads/main.zip",
            "local_path": "data/squall/",
            "file_format": "json",
            "language": "en"
        }
    }
    
    def __init__(self, data_root: str = None):
        """
        初始化数据集加载器
        
        Args:
            data_root: 数据集存储的根目录
        """
        self.data_root = data_root or "./"
        os.makedirs(self.data_root, exist_ok=True)
        self.datasets = {}
        
    def download_dataset(self, dataset_name: str, force_download: bool = False) -> bool:
        """
        下载指定的数据集
        
        Args:
            dataset_name: 数据集名称
            force_download: 是否强制重新下载
            
        Returns:
            下载是否成功
        """
        if dataset_name not in self.DATASET_CONFIGS:
            logger.error(f"未知数据集: {dataset_name}")
            return False
            
        config = self.DATASET_CONFIGS[dataset_name]
        local_path = os.path.join(self.data_root, config["local_path"])
        
        if os.path.exists(local_path) and not force_download:
            logger.info(f"数据集 {dataset_name} 已存在于 {local_path}")
            return True
            
        os.makedirs(local_path, exist_ok=True)
        
        # 检查是否需要手动下载
        if "manual_download" in config:
            logger.error(f"数据集 {dataset_name} 需要手动下载，请访问 {config['url']}")
            return False
            
        try:
            # 下载数据集
            zip_path = os.path.join(local_path, f"{dataset_name}.zip")
            logger.info(f"正在下载 {dataset_name} 到 {zip_path}...")
            
            # 使用带有进度条的下载
            with urllib.request.urlopen(config["url"]) as response, open(zip_path, 'wb') as out_file:
                file_size = int(response.info().get('Content-Length', -1))
                downloaded = 0
                block_size = 8192  # 8KB
                
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    downloaded += len(buffer)
                    out_file.write(buffer)
                    # 简单进度显示
                    if file_size > 0:
                        percent = downloaded * 100 / file_size
                        if percent % 10 == 0:  # 每10%显示一次
                            logger.info(f"下载进度: {percent:.1f}%")
            
            logger.info(f"数据集 {dataset_name} 下载完成")
            
            # 验证并解压数据集
            if not os.path.exists(zip_path):
                logger.error(f"下载文件不存在: {zip_path}")
                return False
                
            # 检查文件类型并解压
            if zipfile.is_zipfile(zip_path):
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(local_path)
                logger.info(f"数据集 {dataset_name} 成功解压")
                return True
            elif tarfile.is_tarfile(zip_path):
                with tarfile.open(zip_path, 'r') as tar_ref:
                    tar_ref.extractall(local_path)
                logger.info(f"数据集 {dataset_name} 成功解压")
                return True
            else:
                # 验证下载内容
                is_valid = self._validate_downloaded_file(zip_path)
                if not is_valid:
                    logger.error(f"下载的文件 {zip_path} 无效或格式不支持")
                    return False
                logger.warning(f"文件 {zip_path} 不是标准压缩格式，但验证通过，请手动检查")
                return True
                
        except Exception as e:
            logger.error(f"下载数据集 {dataset_name} 失败: {str(e)}")
            return False
    
    def _load_chase(self) -> pd.DataFrame:
        """加载CHASE数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["chase"]["local_path"])
        
        # 读取训练集和测试集
        train_file = os.path.join(path, "train.json")
        dev_file = os.path.join(path, "dev.json")
        
        data = []
        for file_path in [train_file, dev_file]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for item in file_data:
                        data.append({
                            'question': item['question'],
                            'query': item['query'],
                            'db_id': item.get('db_id', ''),
                            'db_schema': item.get('db_schema', {}),
                            'split': 'train' if file_path == train_file else 'dev'
                        })
        
        return pd.DataFrame(data)
    
    def _load_cspider(self) -> pd.DataFrame:
        """加载CSpider数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["cspider"]["local_path"])
        
        # 读取训练集和测试集
        train_file = os.path.join(path, "train.json")
        dev_file = os.path.join(path, "dev.json")
        
        data = []
        for file_path, split in [(train_file, 'train'), (dev_file, 'dev')]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for item in file_data:
                        data.append({
                            'question': item['question'],
                            'query': item['query'],
                            'db_id': item.get('db_id', ''),
                            'db_schema': {},  # 需要从数据库文件中提取
                            'split': split
                        })
        
        return pd.DataFrame(data)
    
    def _load_dusql(self) -> pd.DataFrame:
        """加载DuSQL数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["dusql"]["local_path"])
        
        # 读取训练集和测试集
        train_file = os.path.join(path, "train.json")
    
    
    def load_dataset(self, dataset_name: str, download_if_missing: bool = True) -> Optional[pd.DataFrame]:
        """
        加载指定的数据集
        
        Args:
            dataset_name: 数据集名称
            download_if_missing: 若数据集不存在是否下载
            
        Returns:
            加载的数据集，失败则返回None
        """
        if dataset_name in self.datasets:
            return self.datasets[dataset_name]
            
        if dataset_name not in self.DATASET_CONFIGS:
            logger.error(f"未知数据集: {dataset_name}")
            return None
            
        local_path = os.path.join(self.data_root, self.DATASET_CONFIGS[dataset_name]["local_path"])
        
        if not os.path.exists(local_path):
            if download_if_missing:
                success = self.download_dataset(dataset_name)
                if not success:
                    return None
            else:
                logger.error(f"数据集 {dataset_name} 不存在于 {local_path}")
                return None
        
        # 根据数据集名称调用相应的加载方法
        loader_method = f"_load_{dataset_name}"
        if hasattr(self, loader_method):
            df = getattr(self, loader_method)()
            if df is not None:
                self.datasets[dataset_name] = df
                logger.info(f"成功加载数据集 {dataset_name}，共 {len(df)} 条记录")
                return df
            
            logger.error(f"数据集 {dataset_name} 加载失败")
            return None
        else:
            logger.error(f"未实现数据集 {dataset_name} 的加载方法")
            return None
    
    def load_multiple_datasets(
        self,
        dataset_names: List[str],
        languages: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        加载多个数据集并合并
        
        Args:
            dataset_names: 数据集名称列表
            languages: 指定要加载的语言，如["zh", "en"]
            
        Returns:
            合并后的数据集
        """
        dfs = []
        
        for name in dataset_names:
            if languages:
                # 检查数据集语言是否在指定语言列表中
                lang = self.DATASET_CONFIGS.get(name, {}).get("language", "")
                if lang not in languages:
                    continue
                    
            df = self.load_dataset(name)
            if df is not None:
                # 添加数据集来源标识
                df['source'] = name
                dfs.append(df)
                
        if not dfs:
            return pd.DataFrame()
            
        return pd.concat(dfs, ignore_index=True)
    
    def get_training_data(self, format: str = "huggingface") -> Dict:
        """
        将加载的数据集转换为训练格式
        
        Args:
            format: 输出格式，支持"huggingface"、"openai"等
            
        Returns:
            格式化后的训练数据
        """
        if not self.datasets:
            logger.error("没有加载任何数据集")
            return {}
            
        # 合并所有数据集
        all_data = pd.concat(self.datasets.values(), ignore_index=True)
        
        if format == "huggingface":
            # 转换为HuggingFace数据集格式
            return {
                "train": {
                    "question": all_data[all_data['split'] == 'train']['question'].tolist(),
                    "query": all_data[all_data['split'] == 'train']['query'].tolist(),
                    "db_id": all_data[all_data['split'] == 'train']['db_id'].tolist()
                },
                "validation": {
                    "question": all_data[all_data['split'] == 'dev']['question'].tolist(),
                    "query": all_data[all_data['split'] == 'dev']['query'].tolist(),
                    "db_id": all_data[all_data['split'] == 'dev']['db_id'].tolist()
                }
            }
        elif format == "openai":
            # 转换为OpenAI fine-tuning格式
            train_data = []
            for _, row in all_data[all_data['split'] == 'train'].iterrows():
                train_data.append({
                    "messages": [
                        {"role": "user", "content": f"数据库: {row['db_id']}\n问题: {row['question']}"},
                        {"role": "assistant", "content": row['query']}
                    ]
                })
            return train_data
        else:
            logger.error(f"不支持的格式: {format}")
            return {}
    
    def _validate_downloaded_file(self, file_path: str, expected_type: str = "zip") -> bool:
        """验证下载的文件是否有效
        
        Args:
            file_path: 文件路径
            expected_type: 期望的文件类型 (zip, tar等)
            
        Returns:
            文件是否有效
        """
        if not os.path.exists(file_path):
            return False
            
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        if file_size < 1000:  # 小于1KB的文件可能是错误页面
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(100)
                if '<html' in content.lower() or '<!doctype html' in content.lower():
                    logger.error(f"下载的文件似乎是HTML页面而非{expected_type}文件")
                    return False
                    
        if expected_type == "zip" and not zipfile.is_zipfile(file_path):
            return False
        elif expected_type == "tar" and not tarfile.is_tarfile(file_path):
            return False
            
        return True

    # 添加新的数据集加载方法
    def _load_nl2sql_cn(self) -> pd.DataFrame:
        """加载中文NL2SQL数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["nl2sql-cn"]["local_path"])
        
        # 找到master分支下的数据目录
        for root, dirs, files in os.walk(path):
            if "data" in dirs:
                data_dir = os.path.join(root, "data")
                break
        else:
            data_dir = path
            
        train_file = os.path.join(data_dir, "train.json")
        dev_file = os.path.join(data_dir, "val.json")
        
        data = []
        for file_path, split in [(train_file, 'train'), (dev_file, 'dev')]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for item in file_data:
                        data.append({
                            'question': item['question'],
                            'query': item.get('sql', item.get('query', '')),  # 兼容不同字段名
                            'db_id': item.get('table_id', item.get('db_id', '')),
                            'db_schema': item.get('table', {}),
                            'split': split
                        })
        
        return pd.DataFrame(data)
    
    def _load_cosql(self) -> pd.DataFrame:
        """加载CoSQL对话式SQL数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["cosql"]["local_path"])
        
        # 找到数据文件
        train_file = os.path.join(path, "cosql_train.json") 
        dev_file = os.path.join(path, "cosql_dev.json")
        
        data = []
        for file_path, split in [(train_file, 'train'), (dev_file, 'dev')]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for dialog in file_data:
                        db_id = dialog.get('database_id', '')
                        # 处理对话历史
                        context = []
                        for i, turn in enumerate(dialog.get('interaction', [])):
                            question = turn.get('utterance', '')
                            query = turn.get('query', '')
                            context_str = ' '.join(context) if context else ''
                            
                            data.append({
                                'question': question,
                                'context': context_str,  # 前面对话的历史
                                'query': query,
                                'db_id': db_id,
                                'turn_id': i,
                                'dialog_id': dialog.get('id', ''),
                                'split': split,
                                'is_conversational': True
                            })
                            
                            # 更新对话历史
                            context.append(question)
        
        return pd.DataFrame(data)
    
    def _load_sparc(self) -> pd.DataFrame:
        """加载SParC上下文相关SQL数据集"""
        path = os.path.join(self.data_root, self.DATASET_CONFIGS["sparc"]["local_path"])
        
        # 找到数据文件
        train_file = os.path.join(path, "train.json")
        dev_file = os.path.join(path, "dev.json")
        
        data = []
        for file_path, split in [(train_file, 'train'), (dev_file, 'dev')]:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    for dialog in file_data:
                        db_id = dialog.get('database_id', '')
                        # 处理对话历史
                        context = []
                        for i, (question, query) in enumerate(zip(
                            dialog.get('interaction', []),
                            dialog.get('interaction_query', [])
                        )):
                            context_str = ' '.join(context) if context else ''
                            
                            data.append({
                                'question': question,
                                'context': context_str,  # 前面对话的历史
                                'query': query,
                                'db_id': db_id,
                                'turn_id': i,
                                'dialog_id': dialog.get('id', ''),
                                'split': split,
                                'is_conversational': True
                            })
                            
                            # 更新对话历史
                            context.append(question)
        
        return pd.DataFrame(data)
    
    def get_conversational_data(self) -> pd.DataFrame:
        """
        获取所有对话式数据集
        
        Returns:
            包含对话上下文的数据集
        """
        conversational_datasets = []
        
        # 加载所有带对话特性的数据集
        for name, config in self.DATASET_CONFIGS.items():
            if config.get('is_conversational', False):
                df = self.load_dataset(name)
                if df is not None:
                    conversational_datasets.append(df)
        
        if not conversational_datasets:
            return pd.DataFrame()
            
        return pd.concat(conversational_datasets, ignore_index=True)