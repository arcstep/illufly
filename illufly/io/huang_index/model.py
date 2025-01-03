from typing import Optional, Dict, Any, ClassVar, Type
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
import uuid

from .patterns import KeyPattern, RocksDBConfig

class HuangIndexModel(BaseModel):
    """黄索引基础模型
    
    用法示例:
    ```python
    class User(HuangIndexModel):
        __collection__ = "users"
        __namespace__ = "user"
        __key_pattern__ = KeyPattern.PREFIX_INFIX_ID
        __rocksdb_config__ = RocksDBConfig(
            collection_name="users"
        )
        
        name: str
        age: int
        email: Optional[str] = None
        
    # 创建用户实例
    user = User(
        name="张三",
        age=30,
        infix="org_123"  # 组织ID作为中缀
    )
    print(user.key)  # 输出: user:org_123:{uuid}
    ```
    """
    
    # 类级别的元数据配置
    __collection__: ClassVar[str] = "default"  # 默认集合名
    __key_pattern__: ClassVar[KeyPattern] = KeyPattern.PREFIX_ID  # 默认键模式
    __namespace__: ClassVar[str] = "model"  # 默认命名空间
    __rocksdb_config__: ClassVar[RocksDBConfig] = RocksDBConfig(
        collection_name="default"
    )
    
    # 实例级别的键结构元数据
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    infix: Optional[str] = None
    suffix: Optional[str] = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    
    # Pydantic 配置
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow'
    )
    
    @property
    def key(self) -> str:
        """生成存储键"""
        pattern = self.__key_pattern__
        parts = []
        
        if pattern == KeyPattern.PREFIX_ID:
            parts = [self.__namespace__, self.id]
        elif pattern == KeyPattern.PREFIX_ID_SUFFIX:
            parts = [self.__namespace__, self.id, self.suffix]
        elif pattern == KeyPattern.PREFIX_INFIX_ID:
            parts = [self.__namespace__, self.infix, self.id]
        elif pattern == KeyPattern.PREFIX_INFIX_ID_SUFFIX:
            parts = [self.__namespace__, self.infix, self.id, self.suffix]
        elif pattern == KeyPattern.PREFIX_PATH_VALUE:
            parts = [self.__namespace__, self.infix or "path", self.id]
        elif pattern == KeyPattern.PREFIX_INFIX_PATH_VALUE:
            parts = [self.__namespace__, self.infix, "path", self.id]
            
        return ":".join(str(p).strip(":") for p in parts if p)
    
    def model_dump_meta(self) -> Dict[str, Any]:
        """导出元数据"""
        return {
            "id": self.id,
            "infix": self.infix,
            "suffix": self.suffix,
            "key": self.key,
            "collection": self.__collection__,
            "namespace": self.__namespace__,
            "key_pattern": self.__key_pattern__.value
        }
    
    @classmethod
    def get_rocksdb_config(cls) -> RocksDBConfig:
        """获取 RocksDB 配置"""
        return cls.__rocksdb_config__ 