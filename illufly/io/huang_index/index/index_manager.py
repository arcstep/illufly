from typing import Type, Any, Optional, Dict, List, get_origin, Union, Iterator, Set
from pydantic import BaseModel

from ..base_rocksdb import BaseRocksDB
from .accessor import AccessorRegistry
from .path_parser import PathParser
from datetime import datetime 

import logging

class IndexManager:
    INDEX_CF = "indexes"      # 正向索引列族
    REVERSE_CF = "reverse"    # 反向索引列族
    INDEX_METADATA_KEY = "index_metadata"  # 系统列族中的元数据键
    
    # 关键标识符
    KEY_IDENTIFIER = ":key:"  # 用于分隔索引和实际键的标识符
    
    # 正向索引格式（添加 key: 标识符）
    INDEX_KEY_FORMAT = "idx:{collection}:{field}:{value}:key:{key}"
    
    # 反向索引格式（同样添加 key: 标识符）
    REVERSE_KEY_FORMAT = "rev:{collection}:{field}:{value}:idx:{collection}:{field}:{value}:key:{key}"
    
    # 反向索引前缀格式（用于查找）
    REVERSE_PREFIX_FORMAT = "rev:{collection}:{field}:{value}"
    
    # 前缀格式常量
    INDEX_PREFIX_FORMAT = "idx:{collection}"
    INDEX_FIELD_PREFIX_FORMAT = "idx:{collection}:{field}"
    
    def __init__(self, db: BaseRocksDB, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self.db = db
        self._model_indexes = self._load_model_indexes()
        self._accessor_registry = AccessorRegistry()
        self._path_parser = PathParser()
        
    def _load_model_indexes(self) -> Dict[Type, Set[str]]:
        """从系统列族加载索引配置"""
        try:
            system_cf = self.db.get_collection(self.db.SYSTEM_CF)
            metadata = system_cf.get(self.INDEX_METADATA_KEY, {})
            # 转换为集合
            return {k: set(v) for k, v in metadata.items()}
        except Exception as e:
            self._logger.error(f"Failed to load index metadata: {e}")
            return {}
            
    def _save_model_indexes(self) -> None:
        """保存索引配置到系统列族"""
        try:
            system_cf = self.db.get_collection(self.db.SYSTEM_CF)
            # 转换回列表以便序列化
            metadata = {k: list(v) for k, v in self._model_indexes.items()}
            system_cf[self.INDEX_METADATA_KEY] = metadata
            self._logger.info(f"Saved index metadata: {metadata}")
        except Exception as e:
            self._logger.error(f"Failed to save index metadata: {e}")
            raise

    def _get_base_type(self, model_class: Type) -> Type:
        """获取基础类型"""
        self._logger.info(f"获取基础类型: {model_class}")
        
        # 处理 typing 类型
        if hasattr(model_class, '__origin__'):
            self._logger.info(f"处理 typing 类型: origin={model_class.__origin__}")
            return model_class.__origin__
            
        # 处理内置类型
        if model_class in (dict, Dict):
            self._logger.info("统一使用 dict 作为基础类型")
            return dict
            
        # 其他类型保持不变
        return model_class

    def register_model_index(self, model_class: Type, field_path: str):
        """注册模型的索引配置"""
        self._logger.info(f"开始注册索引: 类型={model_class}, 字段={field_path}")
        self._logger.info(f"当前已注册的索引: {self._model_indexes}")

        # 验证字段路径的语法是否合法
        try:
            path_segments = self._path_parser.parse(field_path)
            self._logger.info(f"字段路径 '{field_path}' 解析结果: {path_segments}")
        except ValueError as e:
            self._logger.error(f"字段路径 '{field_path}' 格式无效: {str(e)}")
            raise ValueError(f"无效的字段路径 '{field_path}': {str(e)}")

        # 验证字段路径是否可以访问到属性值
        try:
            self._accessor_registry.validate_path(model_class, field_path)
            self._logger.info("字段路径验证通过")
        except Exception as e:
            self._logger.error(f"字段路径验证失败: {e}")
            raise

        # 注册索引
        base_type = self._get_base_type(model_class)
        self._logger.info(f"基础类型: {base_type}")
        self._logger.info(f"model_class 类型: {type(model_class)}")
        if hasattr(model_class, '__origin__'):
            self._logger.info(f"origin: {model_class.__origin__}, args: {model_class.__args__}")

        if base_type not in self._model_indexes:
            self._logger.info(f"为基础类型 {base_type} 创建新的索引集合")
            self._model_indexes[base_type] = set()
        self._model_indexes[base_type].add(field_path)

        # 同时注册类型提示版本（如果不同的话）
        if model_class != base_type:
            self._logger.info(f"注册类型提示版本: {model_class}")
            if model_class not in self._model_indexes:
                self._model_indexes[model_class] = self._model_indexes[base_type]

        self._logger.info(f"完成索引注册: 类型={model_class}, 基础类型={base_type}, 字段={field_path}")
        self._logger.info(f"更新后的索引配置: {self._model_indexes}")

        # 保存更新后的索引配置
        self._save_model_indexes()

    def _validate_key(self, key: str) -> None:
        """验证键是否包含保留的关键标识符
        
        Args:
            key: 要验证的键
            
        Raises:
            ValueError: 当键包含关键标识符时
        """
        if self.KEY_IDENTIFIER in key:
            raise ValueError(
                f"键 '{key}' 包含保留的关键标识符 '{self.KEY_IDENTIFIER}'。"
                "这个序列用于索引解析，不能在键中使用。"
            )
    
    def _make_index_key(self, collection: str, field_path: str, field_value: Any, key: str) -> str:
        """创建索引键"""
        self._validate_key(key)
        return self.INDEX_KEY_FORMAT.format(
            collection=collection,
            field=field_path,
            value=field_value,
            key=key
        )
        
    def _make_reverse_key(self, collection: str, field_path: str, field_value: Any, key: str) -> str:
        """创建反向索引键"""
        self._validate_key(key)
        return self.REVERSE_KEY_FORMAT.format(
            collection=collection,
            field=field_path,
            value=field_value,
            key=key
        )
        
    def _make_index_prefix(self, collection: str, field_path: str = "") -> str:
        """创建索引前缀"""
        if field_path:                
            return self.INDEX_FIELD_PREFIX_FORMAT.format(
                collection=collection,
                field=field_path
            )
        return self.INDEX_PREFIX_FORMAT.format(collection=collection)
    
    def _make_reverse_prefix(self, collection: str, field_path: str = "", field_value: Any = None) -> str:
        """创建反向索引前缀
        
        Args:
            collection: 集合名称
            field_path: 可选的字段路径
            field_value: 可选的字段值
            
        Returns:
            str: 反向索引前缀
        """
        if field_path and field_value is not None:
            return self.REVERSE_PREFIX_FORMAT.format(
                collection=collection,
                field=field_path,
                value=field_value
            )
        elif field_path:
            return f"rev:{collection}:{field_path}"
        return f"rev:{collection}"
        
    def update_indexes(self, collection: str, key: str, old_value: Any, new_value: Any):
        """更新索引"""
        self._logger.info(f"开始更新索引: collection={collection}, key={key}")
        self._logger.info(f"旧值类型: {type(old_value) if old_value is not None else 'None'}")
        self._logger.info(f"新值类型: {type(new_value) if new_value is not None else 'None'}")
        
        # 处理删除操作
        if new_value is None:
            if old_value is None:
                self._logger.info("新旧值都为空，无需更新索引")
                return
            value_type = type(old_value)
            self._logger.info(f"删除操作，使用旧值类型: {value_type}")
        else:
            value_type = type(new_value)
            self._logger.info(f"使用新值类型: {value_type}")
        
        # 获取基础类型
        base_type = self._get_base_type(value_type)
        self._logger.info(f"基础类型: {base_type}")
        
        # 检查是否需要索引处理
        if value_type not in self._model_indexes and base_type not in self._model_indexes:
            self._logger.warning(f"类型 {value_type} (基础类型 {base_type}) 没有注册任何索引")
            return
            
        # 使用已注册的索引配置
        indexes = self._model_indexes.get(value_type) or self._model_indexes[base_type]
        self._logger.info(f"使用索引配置: {indexes}")
        
        with self.db.batch_write() as batch:
            # 获取列族句柄
            index_cf = self.db.get_cf_handle(self.INDEX_CF)
            reverse_cf = self.db.get_cf_handle(self.REVERSE_CF)
            
            # 1. 删除旧索引
            if old_value is not None:
                self._logger.info("开始删除旧索引")
                for field_path in indexes:
                    try:
                        old_field_value = self._accessor_registry.get_field_value(old_value, field_path)
                        if old_field_value is not None:
                            # 删除正向索引
                            old_index_key = self._make_index_key(collection, field_path, old_field_value, key)
                            self._logger.info(f"删除旧正向索引: {old_index_key}")
                            batch.delete(old_index_key.encode(), column_family=index_cf)
                            
                            # 删除反向索引
                            old_reverse_key = self._make_reverse_key(collection, field_path, old_field_value, key)
                            self._logger.info(f"删除旧反向索引: {old_reverse_key}")
                            batch.delete(old_reverse_key.encode(), column_family=reverse_cf)
                    except Exception as e:
                        self._logger.error(f"删除旧索引时出错: {e}")
            
            # 2. 创建新索引
            if new_value is not None:
                self._logger.info("开始创建新索引")
                for field_path in indexes:
                    try:
                        field_value = self._accessor_registry.get_field_value(new_value, field_path)
                        if field_value is not None:
                            # 创建正向索引
                            index_key = self._make_index_key(collection, field_path, field_value, key)
                            self._logger.info(f"创建正向索引: {index_key}")
                            batch.put(index_key.encode(), None, column_family=index_cf)
                            
                            # 创建反向索引
                            reverse_key = self._make_reverse_key(collection, field_path, field_value, key)
                            self._logger.info(f"创建反向索引: {reverse_key}")
                            batch.put(reverse_key.encode(), None, column_family=reverse_cf)
                    except Exception as e:
                        self._logger.error(f"创建新索引时出错: {e}")
        
        self._logger.info("索引更新完成")
        
        # 验证索引创建结果
        self._logger.info("验证索引创建结果:")
        for index_key in self.db.iter_keys(self.INDEX_CF):
            self._logger.info(f"发现正向索引: {index_key}")
        for reverse_key in self.db.iter_keys(self.REVERSE_CF):
            self._logger.info(f"发现反向索引: {reverse_key}")

    def _get_field_value(self, model: BaseModel, field_path: str) -> Any:
        """获取模型的嵌套字段值"""
        value = model
        for part in field_path.split('.'):
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
        return value 

    def query_by_index(
        self,
        collection: str,
        field_path: str,
        value: Any = None, 
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
        reverse: bool = False
    ) -> Iterator[str]:
        """通过索引查询键"""
        index_key_prefix = self._make_index_key(collection, field_path, value, "")
        self._logger.info(f"查询索引前缀: {index_key_prefix}")
        
        for key in self.db.iter_keys(
            self.INDEX_CF,
            prefix=index_key_prefix,
            start=start,
            end=end,
            limit=limit,
            reverse=reverse
        ):
            parts = key.split(self.KEY_IDENTIFIER)
            if len(parts) == 2:
                target_key = parts[1]
                self._logger.info(f"从索引 {key} 提取目标键: {target_key}")
                yield target_key
            else:
                raise ValueError(f"索引键格式不正确: {key}") 