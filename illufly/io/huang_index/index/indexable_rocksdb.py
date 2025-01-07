from typing import Type, Optional, Iterator, Tuple, Any
from pydantic import BaseModel
from ..base_rocksdb import BaseRocksDB
from .index_manager import IndexManager
from contextlib import contextmanager

class IndexableRocksDB(BaseRocksDB):
    # 索引列族的默认配置
    INDEX_CF_OPTIONS = {
        "write_buffer_size": 64 * 1024 * 1024,  # 64MB
        "max_write_buffer_number": 4,  # 允许更多的写缓冲
        "min_write_buffer_number_to_merge": 1,  # 尽快刷新到L0
        "level0_file_num_compaction_trigger": 8,  # 增加L0文件数触发合并的阈值
        "level0_slowdown_writes_trigger": 17,  # 增加L0文件数减缓写入的阈值
        "level0_stop_writes_trigger": 24,  # 增加L0文件数停止写入的阈值
        "target_file_size_base": 64 * 1024 * 1024,  # 64MB
        "compression_type": "none",  # 禁用压缩，因为索引值都是None
        "bloom_locality": 1,  # 优化布隆过滤器的局部性
        "prefix_extractor": "rocksdb.CappedPrefix.512"  # 使用可变长度前缀，最大512字节
    }
    
    def __init__(self, path: str, *args, **kwargs):
        """初始化可索引的RocksDB
        
        Args:
            path: 数据库路径
            *args: 传递给父类的位置参数
            **kwargs: 传递给父类的关键字参数
        """
        # 确保在打开数据库前就定义好所有必需的列族
        required_column_families = {
            IndexManager.INDEX_CF: self.INDEX_CF_OPTIONS.copy(),  # 索引列族配置
            IndexManager.REVERSE_CF: self.INDEX_CF_OPTIONS.copy()  # 反向索引列族配置（使用相同配置）
        }
        
        # 合并用户提供的列族配置
        if 'collections' in kwargs:
            user_collections = kwargs.pop('collections')
            for cf_name, options in user_collections.items():
                if cf_name in required_column_families:
                    # 更新必需列族的配置
                    required_column_families[cf_name].update(options)
                else:
                    # 添加其他列族
                    required_column_families[cf_name] = options
        
        # 调用父类初始化，传递合并后的配置
        super().__init__(
            path,
            collections=required_column_families,  # 只传递必需的列族配置
            *args,
            **kwargs
        )
        
        # 初始化索引管理器
        self.index_manager = IndexManager(self, logger=self._logger)
        self._in_batch = False
        self._pending_index_updates = []
        
        self._logger.info(
            f"Initialized IndexableRocksDB with indexes at: {path}"
        )
    
    def register_model_index(self, model_class: Type[BaseModel], field_path: str):
        """注册模型索引"""
        self.index_manager.register_model_index(model_class, field_path)
    
    def all_indexes(self, collection: str, prefix: str="") -> Iterator[str]:
        """迭代索引"""
        if prefix:
            # 使用字段前缀
            full_prefix = self.index_manager._make_index_prefix(collection, prefix)
        else:
            # 使用集合前缀
            full_prefix = self.index_manager._make_index_prefix(collection)
        self._logger.info(f"查询索引前缀: {full_prefix}")
        return self.iter_keys(IndexManager.INDEX_CF, prefix=full_prefix)

    def all_reverse_indexes(self, collection: str, prefix: str="") -> Iterator[str]:
        """迭代反向索引"""
        full_prefix = self.index_manager._make_reverse_prefix(collection)
        if prefix:
            full_prefix = f"{full_prefix}:{prefix}"
        self._logger.info(f"查询反向索引前缀: {full_prefix}")
        return self.iter_keys(IndexManager.REVERSE_CF, prefix=full_prefix)

    @contextmanager
    def batch_write(self) -> Iterator[None]:
        """重写批处理方法"""
        self._in_batch = True
        self._pending_index_updates = []
        
        try:
            with super().batch_write() as batch:
                yield batch
                # 在批处理提交前执行所有待处理的索引更新
                for collection, key, old_value, new_value in self._pending_index_updates:
                    self.index_manager.update_indexes(collection, key, old_value, new_value)
        finally:
            self._in_batch = False
            self._pending_index_updates = []
            
    def set(self, collection: str, key: str, value: BaseModel):
        """设置对象时自动更新索引"""
        self._logger.info(f"开始设置值: collection={collection}, key={key}, value={value}")

        self.index_manager._validate_key(key)
        try:
            old_value = self.get(collection, key)
            self._logger.info(f"获取到旧值: {old_value}")
        except (ValueError, Exception) as e:
            self._logger.info(f"获取旧值失败: {e}")
            old_value = None
            
        # 保存新值
        super().set(collection, key, value)
        self._logger.info("新值已保存")
        
        # 如果在批处理中，延迟索引更新
        if self._in_batch:
            self._logger.info("在批处理中，延迟索引更新")
            self._pending_index_updates.append((collection, key, old_value, value))
        else:
            # 不在批处理中，直接更新索引
            self._logger.info("开始更新索引")
            self.index_manager.update_indexes(collection, key, old_value, value)
            self._logger.info("索引更新完成")
        
    def delete(self, collection: str, key: str):
        """删除对象时自动清理索引"""
        # 获取旧值
        old_value = self.get(collection, key)
        
        if old_value:
            # 清理索引
            self.index_manager.update_indexes(collection, key, old_value, None)
        
        # 删除原始值
        super().delete(collection, key)
        
    def iter_keys(
        self,
        collection: str,
        prefix: Optional[str] = None,
        field_path: Optional[str] = None,
        field_value: Optional[Any] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
        reverse: bool = False,
        range_type: str = "[]"
    ) -> Iterator[str]:
        """扩展的键迭代方法，支持索引查询
        
        Args:
            collection: 集合名称
            prefix: 键前缀（与索引查询互斥）
            field_path: 索引字段路径
            field_value: 索引字段值
            limit: 限制返回数量
            reverse: 是否反向迭代
            range_type: 区间类型，支持:
                - "[]": 闭区间 [start, end]（默认）
                - "[)": 左闭右开区间 [start, end)
                - "(]": 左开右闭区间 (start, end]
                - "()": 开区间 (start, end)
        """
        if field_path is not None:
            # 使用索引查询
            yield from self.index_manager.query_by_index(
                collection, field_path, field_value, start, end, limit, reverse
            )
        else:
            # 使用普通前缀查询
            yield from super().iter_keys(
                collection, prefix, limit=limit, reverse=reverse, start=start, end=end, range_type=range_type
            )
    
    def all(self, collection: str, prefix: Optional[str] = None,
            field_path: Optional[str] = None, field_value: Optional[Any] = None,
            start: Optional[str] = None, end: Optional[str] = None,
            limit: Optional[int] = None, reverse: bool = False) -> Iterator[Tuple[str, Any]]:
        """扩展的查询方法，支持索引查询"""
        if limit is not None and limit > self.MAX_ITEMS_LIMIT:
            raise ValueError(f"返回条数限制不能超过 {self.MAX_ITEMS_LIMIT}")
            
        return [(key, self.get(collection, key)) 
                for key in self.iter_keys(
                    collection,
                    limit=limit, reverse=reverse,
                    prefix=prefix,
                    field_path=field_path, field_value=field_value,
                    start=start, end=end
                )]
    
    def first(self, collection: str, prefix: Optional[str] = None,
            field_path: Optional[str] = None, field_value: Optional[Any] = None,
            start: Optional[str] = None, end: Optional[str] = None) -> Optional[Tuple[str, Any]]:
        """获取第一个匹配的记录"""
        
        results = list(self.all(
            collection,
            prefix=prefix,
            field_path=field_path, field_value=field_value,
            start=start, end=end,
            limit=1, reverse=False
        ))
        
        return results[0] if results else None
    
    def last(self, collection: str, prefix: Optional[str] = None,
            field_path: Optional[str] = None, field_value: Optional[Any] = None,
            start: Optional[str] = None, end: Optional[str] = None) -> Optional[Tuple[str, Any]]:
        """获取最后一个匹配的记录"""

        results = list(self.all(
            collection,
            prefix=prefix,
            field_path=field_path, field_value=field_value,
            start=start, end=end,
            limit=1, reverse=True
        ))
        
        return results[0] if results else None

