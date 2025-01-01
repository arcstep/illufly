from typing import Optional, Any, List, Dict, Set, Iterator, Tuple
from rocksdict import Rdict, Options, ColumnFamily, ReadOptions
import json
from pathlib import Path

class RocksDBStorage:
    """RocksDB存储后端
    
    支持通过segment管理不同的数据集，每个segment可以有独立的配置。
    使用RocksDB的Column Families实现segment隔离。
    
    键格式设计：
    1. 分组前缀: "group:subgroup:"
    2. 时间序列: "group:YYYY-MM-DD:"
    3. 复合键: "group:field:value:"
    """
    
    def __init__(
        self,
        db_path: str,
        default_options: Optional[Dict[str, Any]] = None
    ):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 存储segment配置
        self._segment_configs: Dict[str, Options] = {}
        self._segment_cfs: Dict[str, ColumnFamily] = {}
        
        # 默认配置
        self._default_options = default_options or {
            'block_cache_size': 512 * 1024 * 1024,  # 512MB
            'write_buffer_size': 64 * 1024 * 1024,  # 64MB
            'max_write_buffers': 3,
        }
        
        # 打开数据库
        self._db = self._open_db()
        
    def _open_db(self) -> Rdict:
        """打开数据库，确保所有segment的列族存在"""
        # 获取现有的列族
        existing_cfs = Rdict.list_cf(str(self._db_path))
        
        # 打开数据库
        opts = self._create_options(self._default_options)
        db = Rdict(str(self._db_path), opts)
        
        # 初始化默认列族
        if 'default' not in existing_cfs:
            db.create_cf('default', self._create_options(self._default_options))
            
        return db
        
    def _create_options(self, config: Dict[str, Any]) -> Options:
        """根据配置创建Options对象"""
        opts = Options()
        opts.set_block_cache_size(config['block_cache_size'])
        opts.set_write_buffer_size(config['write_buffer_size'])
        opts.set_max_write_buffer_number(config['max_write_buffers'])
        return opts
        
    def create_segment(self, segment: str, options: Optional[Dict[str, Any]] = None) -> None:
        """创建新的segment
        
        Args:
            segment: segment名称
            options: segment特定的配置选项
        """
        if segment in self._segment_cfs:
            raise ValueError(f"Segment {segment} 已存在")
            
        # 使用自定义配置或默认配置
        config = options or self._default_options
        opts = self._create_options(config)
        
        # 创建新的列族
        cf = self._db.create_cf(segment, opts)
        
        # 保存配置和列族引用
        self._segment_configs[segment] = config
        self._segment_cfs[segment] = cf
        
    def get_segment(self, segment: str) -> ColumnFamily:
        """获取segment的列族对象"""
        if segment not in self._segment_cfs:
            # 如果segment不存在，使用默认配置创建
            self.create_segment(segment)
        return self._segment_cfs[segment]
        
    def get(self, segment: str, key: str) -> Optional[Any]:
        """从指定segment获取值"""
        cf = self.get_segment(segment)
        value = cf.get(key.encode())
        if value is None:
            return None
        return json.loads(value.decode())
        
    def set(self, segment: str, key: str, value: Any) -> None:
        """写入值到指定segment"""
        cf = self.get_segment(segment)
        encoded_value = json.dumps(value).encode()
        cf[key.encode()] = encoded_value
        
    def list_segments(self) -> Set[str]:
        """列出所有segment"""
        return set(self._segment_cfs.keys())
        
    def clear_segment(self, segment: str) -> None:
        """清空指定segment的数据"""
        cf = self.get_segment(segment)
        for key in cf.keys():
            del cf[key]
            
    def drop_segment(self, segment: str) -> None:
        """删除整个segment"""
        if segment in self._segment_cfs:
            self._db.drop_cf(segment)
            del self._segment_configs[segment]
            del self._segment_cfs[segment]
            
    def close(self) -> None:
        """关闭数据库"""
        self._db.close()
        
    def make_key(self, *parts: str) -> str:
        """构造复合键
        
        Args:
            parts: 键的各个部分
            
        Returns:
            使用冒号连接的复合键
            
        Example:
            >>> make_key("users", "active", "2024")
            "users:active:2024"
        """
        return ":".join(part.strip(":") for part in parts if part)
    
    def iter_segment(
        self, 
        segment: str, 
        group: Optional[str] = None,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Iterator[Tuple[str, Any]]:
        """迭代指定segment中的数据
        
        Args:
            segment: segment名称
            group: 分组前缀 (例如: "users", "orders")
            prefix: 完整的键前缀 (例如: "users:active:")
            suffix: 键尾部匹配 (例如: ":2024")
            start: 起始键（包含）
            end: 结束键（不包含）
            
        Examples:
            # 按分组迭代
            iter_segment("main", group="users")  # 匹配 "users:*"
            
            # 按复合前缀迭代
            iter_segment("main", prefix="users:active:")  # 匹配 "users:active:*"
            
            # 按后缀迭代（注意：这需要全表扫描）
            iter_segment("main", suffix=":2024")  # 匹配 "*:2024"
            
            # 范围查询（在同一分组内）
            iter_segment("main", 
                       group="users",
                       start="A",
                       end="B")  # 匹配 "users:[A-B)*"
        """
        cf = self.get_segment(segment)
        read_opts = ReadOptions()
        
        # 构造实际的前缀
        actual_prefix = None
        if group:
            actual_prefix = f"{group}:"
        elif prefix:
            actual_prefix = prefix
            
        if actual_prefix:
            read_opts.set_prefix_same_as_start(True)
            
        # 构造实际的起始键
        actual_start = None
        if start and actual_prefix:
            actual_start = f"{actual_prefix}{start}"
        elif start:
            actual_start = start
        elif actual_prefix:
            actual_start = actual_prefix
            
        # 构造实际的结束键
        actual_end = None
        if end and actual_prefix:
            actual_end = f"{actual_prefix}{end}"
        elif end:
            actual_end = end
            
        it = cf.iterator(read_opts)
        
        try:
            if actual_start:
                it.seek(actual_start.encode())
            else:
                it.seek_to_first()
                
            while it.valid():
                key_bytes = it.key()
                key = key_bytes.decode()
                
                # 检查前缀
                if actual_prefix and not key.startswith(actual_prefix):
                    break
                    
                # 检查结束键
                if actual_end and key >= actual_end:
                    break
                    
                # 检查后缀
                if suffix and not key.endswith(suffix):
                    it.next()
                    continue
                    
                value_bytes = it.value()
                value = json.loads(value_bytes.decode())
                
                yield key, value
                it.next()
                
        finally:
            del it
        
    def list_keys(self, segment: str, prefix: Optional[str] = None) -> List[str]:
        """列出segment中的所有键
        
        Args:
            segment: segment名称
            prefix: 可选的键前缀过滤
            
        Returns:
            键列表
        """
        return [key for key, _ in self.iter_segment(segment, prefix=prefix)]
        
    def data_iterator(self, segment: str) -> Iterator[Tuple[str, Dict[str, Any]]]:
        """返回segment的数据迭代器，兼容原有接口
        
        Args:
            segment: segment名称
            
        Yields:
            (key, data) 元组
        """
        yield from self.iter_segment(segment)
