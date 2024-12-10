from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from .models import AgentConfig
from ...chat import ChatQwen
from ...flow import ChatLearn
from ...io import LocalFileEventsHistory, LocalFileMemoryHistory, LocalFileKnowledgeDB
from ...community.faiss import FaissDB
from ...community.dashscope import TextEmbeddings

class AgentFactory:
    """Agent实例创建工厂"""
    
    @staticmethod
    def get_agent_paths(base_path: str, username: str, agent_name: str) -> Dict[str, str]:
        """获取代理相关的所有路径"""
        # base_path 已经包含了用户路径，直接使用 store 子目录
        base_store_path = Path(base_path) / "store"
        
        # 构建路径字典
        paths = {
            'events': str(base_store_path / "hist" / agent_name),
            'memory': str(base_store_path / "memory" / agent_name),
            'knowledge': str(base_store_path / "knowledge")  # knowledge 不需要 agent_name
        }
        
        # 确保所有目录都存在
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        
        return paths

    @staticmethod
    def create_agent(
        username: str,
        agent_type: str,
        agent_name: str,
        base_path: str,
        vectordb_names: List[str] = None,
        **kwargs
    ) -> Tuple[AgentConfig, Any]:
        """创建代理实例和配置
        
        Returns:
            Tuple[AgentConfig, Any]: (配置信息, 实例对象)
        """
        paths = AgentFactory.get_agent_paths(base_path, username, agent_name)

        # 获取所有可用的向量数据库
        all_vectordbs = AgentFactory.list_dbs(username, base_path)
        
        # 根据 vectordb_names 筛选或使用第一个可用的向量数据库
        if vectordb_names:
            vectordbs = [
                db for db in all_vectordbs 
                if db.name in vectordb_names
            ]
        else:
            vectordbs = all_vectordbs[:1] if all_vectordbs else []

        # 创建实例
        if agent_type == "chat":
            instance = ChatQwen(
                name=agent_name,
                vectordbs=vectordbs,
                events_history=LocalFileEventsHistory(paths['events']),
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
        elif agent_type == "learn":
            chat_agent = ChatQwen(
                name=f"{agent_name}_qwen",
                vectordbs=vectordbs,
                memory_history=LocalFileMemoryHistory(paths['memory'])
            )
            instance = ChatLearn(
                chat_agent,
                name=agent_name,
                events_history=LocalFileEventsHistory(paths['events'])
            )
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # 创建配置
        config = AgentConfig(
            name=agent_name,
            agent_type=agent_type,
            description=kwargs.get("description", ""),
            config=kwargs.get("config", {}),
            vectordb_names=[db.name for db in vectordbs],
            events_history_path=paths['events'],
            memory_history_path=paths['memory'],
            created_at=datetime.now(),
            last_used=datetime.now()
        )
        
        return config, instance

    @staticmethod
    def create_db(username: str, db_name: str, base_path: str) -> FaissDB:
        """创建知识库"""
        paths = AgentFactory.get_agent_paths(base_path, username, "")
        db_path = Path(paths['knowledge']) / db_name
        # 确保父目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 创建知识库目录
        db_path.mkdir(exist_ok=True)
        return FaissDB(
            LocalFileKnowledgeDB(db_path),
            embeddings=TextEmbeddings(),
            name=db_path.name
        )

    @staticmethod
    def list_dbs(username: str, base_path: str) -> List[FaissDB]:
        """列出知识库"""
        paths = AgentFactory.get_agent_paths(base_path, username, "")
        knowledge_path = Path(paths['knowledge'])
        return [
            AgentFactory.create_db(username, db_path.name, base_path)
            for db_path in knowledge_path.iterdir()
            if db_path.is_dir() and not db_path.name.startswith('.')
        ]

    @staticmethod
    def cleanup_agent(username: str, agent_name: str, base_path: str):
        """清理代理相关的文件"""
        paths = AgentFactory.get_agent_paths(base_path, username, agent_name)
        
        # 清理事件历史和内存历史
        for path in [paths['events'], paths['memory']]:
            path = Path(path)
            if path.exists():
                import shutil
                shutil.rmtree(path)
