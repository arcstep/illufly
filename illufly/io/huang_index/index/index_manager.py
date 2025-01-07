from typing import Type, Any, Optional, Dict, List, get_origin, Union, Iterator, Set
from pydantic import BaseModel

from ..base_rocksdb import BaseRocksDB
from .accessor import AccessorRegistry
from .path_parser import PathParser
from datetime import datetime 

import logging
import hashlib

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
    
    # 特殊字符替换映射
    SPECIAL_CHARS = {
        '.': '_dot_',
        '[': '_lb_',
        ']': '_rb_',
        '{': '_lcb_',
        '}': '_rcb_',
        ':': '_col_',
        '/': '_sl_',
        '\\': '_bs_',
        '*': '_ast_',
        '?': '_qm_',
        '<': '_lt_',
        '>': '_gt_',
        '|': '_pipe_',
        '"': '_quot_',
        "'": '_apos_'
    }
    
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
        
        # 处理 typing 类型
        if hasattr(model_class, '__origin__'):
            return model_class.__origin__
            
        # 处理内置类型
        if model_class in (dict, Dict):
            return dict
            
        # 其他类型保持不变
        return model_class

    def register_model_index(self, model_class: Type, field_path: str):
        """注册模型的索引配置"""

        # 验证字段路径的语法是否合法
        try:
            path_segments = self._path_parser.parse(field_path)
        except ValueError as e:
            self._logger.error(f"字段路径 '{field_path}' 格式无效: {str(e)}")
            raise ValueError(f"无效的字段路径 '{field_path}': {str(e)}")

        # 验证字段路径是否可以访问到属性值
        try:
            self._accessor_registry.validate_path(model_class, field_path)
        except Exception as e:
            self._logger.error(f"字段路径验证失败: {e}")
            raise

        # 注册索引
        base_type = self._get_base_type(model_class)
        if hasattr(model_class, '__origin__'):
            self._logger.info(f"origin: {model_class.__origin__}, args: {model_class.__args__}")

        if base_type not in self._model_indexes:
            self._model_indexes[base_type] = set()
        self._model_indexes[base_type].add(field_path)

        # 同时注册类型提示版本（如果不同的话）
        if model_class != base_type:
            if model_class not in self._model_indexes:
                self._model_indexes[model_class] = self._model_indexes[base_type]

        self._logger.info(f"完成索引注册: 类型={model_class}, 基础类型={base_type}, 字段={field_path}")

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
    
    @classmethod
    def _escape_special_chars(cls, value: str) -> str:
        """替换字符串中的特殊字符"""
        result = value
        for char, replacement in cls.SPECIAL_CHARS.items():
            result = result.replace(char, replacement)
        return result
    
    @classmethod
    def format_index_value(cls, value: Any, logger=None) -> str:
        """格式化索引值
        
        格式化规则：
        1. None -> "null"
        2. 布尔值 -> "false" 或 "true"
        3. 数值：
            - float('-inf') -> "a" (确保小于所有数值)
            - 负数 -> "a{数值}" (确保小于正数)
            - 0 -> "c0000000000_000000"
            - 正数 -> "c{数值}"
            - float('inf') -> "d" (确保大于所有数值)
            - float('nan') -> "e" (确保排在最后)
        4. 日期时间 -> "t{timestamp:010d}"
        5. 字符串：
            - 空字符串 -> "empty"
            - 长字符串 -> base32编码的MD5哈希
            - 普通字符串 -> 转义后的字符串
        """
        if value is None:
            if logger:
                logger.info(f"格式化空值: {value} -> null")
            return 'null'
            
        if isinstance(value, bool):
            return str(value).lower()  # 使用小写以确保排序一致性
            
        if isinstance(value, (int, float)):
            if isinstance(value, float):
                if value == float('inf'): return 'd'
                if value == float('-inf'): return 'a'
                if value != value: return 'e'
            
            num = float(value)
            if num == 0:
                return 'c0000000000_000000'
            
            abs_num = abs(num)
            int_part = int(abs_num)
            dec_part = int((abs_num - int_part) * 1e6)
            
            if num < 0:
                # 负数：按位对齐做减法
                int_part_str = f"{9999999999 - int_part:010d}"
                dec_part_str = f"{999999 - dec_part:06d}"
                result = f"b{int_part_str}_{dec_part_str}"
            else:
                # 正数：直接格式化
                result = f"c{int_part:010d}_{dec_part:06d}"
            
            if logger:
                logger.info(f"格式化数值 {num} -> {result}")
            return result
            
        if isinstance(value, datetime):
            return f"t{int(value.timestamp()):010d}"
            
        if isinstance(value, str):
            if not value:
                return 'empty'
            if len(value) > 100:
                import base64
                hash_bytes = hashlib.md5(value.encode()).digest()
                return f"h{base64.b32encode(hash_bytes).decode().rstrip('=')}"
            # 添加前缀 's' 以区分字符串类型
            return f"s{cls._escape_special_chars(value)}"
            
        # 其他类型转为字符串
        return f"v{cls._escape_special_chars(str(value))}"

    def _make_index_key(self, collection: str, field_path: str, field_value: Any, key: str) -> str:
        """创建索引键"""
        self._validate_key(key)
        formatted_value = self.format_index_value(field_value, logger=self._logger)
        return self.INDEX_KEY_FORMAT.format(
            collection=collection,
            field=field_path,
            value=formatted_value,
            key=key
        )
        
    def _make_reverse_key(self, collection: str, field_path: str, field_value: Any, key: str) -> str:
        """创建反向索引键"""
        self._validate_key(key)
        formatted_value = self.format_index_value(field_value, logger=self._logger)
        return self.REVERSE_KEY_FORMAT.format(
            collection=collection,
            field=field_path,
            value=formatted_value,
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
        self._logger.info(f"开始更新索引: collection={collection}, key={key}, old_value={old_value}, new_value={new_value}")
        
        # 处理删除操作
        if new_value is None:
            if old_value is None:
                return
            value_type = type(old_value)
            self._logger.info(f"删除操作，使用旧值类型: {value_type}")
        else:
            value_type = type(new_value)
            self._logger.info(f"更新/创建操作，使用新值类型: {value_type}")
        
        # 获取基础类型
        base_type = self._get_base_type(value_type)
        self._logger.info(f"基础类型: {base_type}")
        
        # 检查是否有注册的索引
        if value_type not in self._model_indexes and base_type not in self._model_indexes:
            self._logger.info(f"类型 {value_type} (基础类型 {base_type}) 没有注册任何索引，跳过索引更新")
            return
        
        # 使用已注册的索引配置
        indexes = self._model_indexes.get(value_type) or self._model_indexes[base_type]
        self._logger.info(f"找到注册的索引: {indexes}")
        
        with self.db.batch_write() as batch:
            # 获取列族句柄
            index_cf = self.db.get_cf_handle(self.INDEX_CF)
            reverse_cf = self.db.get_cf_handle(self.REVERSE_CF)
            
            # 1. 删除旧索引
            if old_value is not None:
                for field_path in indexes:
                    try:
                        self._logger.info(f"尝试删除旧索引: field_path={field_path}, old_value={old_value}")
                        if self._accessor_registry.validate_path(old_value.__class__, field_path):
                            old_field_value = self._accessor_registry.get_field_value(old_value, field_path)
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
                for field_path in indexes:
                    try:
                        self._logger.info(f"尝试创建新索引: field_path={field_path}, new_value={new_value}")
                        # 1. 先验证路径语法
                        if not self._accessor_registry.validate_path(new_value.__class__, field_path):
                            self._logger.info(f"属性路径验证失败，跳过创建索引")
                            continue
                            
                        # 2. 尝试获取字段值
                        try:
                            field_value = self._accessor_registry.get_field_value(new_value, field_path)
                        except (KeyError, AttributeError):
                            # 字段不存在，跳过
                            continue
                            
                        # 3. 创建索引
                        index_key = self._make_index_key(collection, field_path, field_value, key)
                        self._logger.info(f"创建正向索引: {index_key}")
                        batch.put(index_key.encode(), None, column_family=index_cf)
                        
                        reverse_key = self._make_reverse_key(collection, field_path, field_value, key)
                        self._logger.info(f"创建反向索引: {reverse_key}")
                        batch.put(reverse_key.encode(), None, column_family=reverse_cf)
                    except Exception as e:
                        self._logger.error(f"创建新索引时出错: {e}")

    def query_by_index(
        self,
        collection: str,
        field_path: str,
        field_value: Any = None, 
        start: Optional[Any] = None,
        end: Optional[Any] = None,
        limit: Optional[int] = None,
        reverse: bool = False
    ) -> Iterator[str]:
        """通过索引查询键
        
        Args:
            collection: 集合名称
            field_path: 索引字段路径
            field_value: 字段精确匹配值
            start: 范围查询起始值
            end: 范围查询结束值
            limit: 限制返回数量
            reverse: 是否反向查询
        
        Raises:
            ValueError: 当指定的字段路径未注册索引时抛出
            ValueError: 当既没有提供 field_value 也没有提供 start/end 时抛出
        """
        # 验证查询参数
        if field_value is None and start is None and end is None:
            error_msg = (
                f"查询字段 {field_path} 时必须提供查询条件："
                f"\n1. 提供 field_value 参数进行精确匹配"
                f"\n2. 提供 start 和/或 end 参数进行范围查询"
            )
            self._logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 验证字段是否已注册索引
        for model_indexes in self._model_indexes.values():
            if field_path in model_indexes:
                break
        else:
            error_msg = (
                f"字段 {field_path} 未注册索引。这可能是因为:"
                f"\n1. 忘记注册该字段的索引"
                f"\n2. 索引注册顺序有误"
                f"\n请使用 register_model_index 注册索引并调用 rebuild_indexes 重建索引。"
                f"\n示例: db.register_model_index(dict, '{field_path}')"
            )
            self._logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 构建基础前缀
        base_prefix = f"idx:{collection}:{field_path}:"
        
        if start is not None or end is not None:
            # 范围查询时，确保只查询指定字段的索引
            start_key = f"{base_prefix}{self.format_index_value(start, logger=self._logger)}:key:" if start is not None else base_prefix
            end_key = f"{base_prefix}{self.format_index_value(end, logger=self._logger)}:key:" if end is not None else base_prefix + "\xff"
            
            self._logger.info(f"范围查询: start={start_key}, end={end_key}")
            
            for key in self.db.iter_keys(
                self.INDEX_CF,
                start=start_key,
                end=end_key,
                limit=limit,
                reverse=reverse,
                range_type="[]"  # 显式指定闭区间
            ):
                parts = key.split(self.KEY_IDENTIFIER)
                if len(parts) == 2:
                    target_key = parts[1]
                    self._logger.info(f"从索引 {key} 提取目标键: {target_key}")
                    yield target_key
                else:
                    raise ValueError(f"索引键格式不正确: {key}")
        else:
            # 精确匹配模式
            formatted_value = self.format_index_value(field_value, logger=self._logger)
            index_key_prefix = f"{base_prefix}{formatted_value}:key:"
            self._logger.info(f"精确匹配查询前缀: {index_key_prefix}")
            
            for key in self.db.iter_keys(
                self.INDEX_CF,
                prefix=index_key_prefix,
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

    def rebuild_indexes(self, collection: str = None):
        """重建索引
        
        用于以下场景:
        1. 新注册索引后，为已有数据建立索引
        2. 修改索引配置后重建索引
        3. 索引损坏后的修复
        
        Args:
            collection: 指定集合名称，如果为 None 则重建所有集合的索引
        """
        self._logger.info(f"开始重建索引: collection={collection}")
        
        # 如果没有指定集合，获取所有集合
        if collection is None:
            collections = self.get_all_collections()
        else:
            collections = [collection]
        
        for coll in collections:
            self._logger.info(f"重建集合 {coll} 的索引")
            # 删除现有索引
            self._clear_collection_indexes(coll)
            
            # 重建索引
            for key, value in self.all(coll):
                self.update_indexes(coll, key, None, value)
        
        self._logger.info("索引重建完成")

    def _clear_collection_indexes(self, collection: str):
        """清除集合的所有索引"""
        prefix = f"idx:{collection}:"
        with self.db.batch_write() as batch:
            # 删除正向索引
            for key in self.db.iter_keys(self.INDEX_CF, prefix=prefix):
                batch.delete(key, column_family=self.db.get_cf_handle(self.INDEX_CF))
            
            # 删除反向索引
            rev_prefix = f"rev:{collection}:"
            for key in self.db.iter_keys(self.REVERSE_CF, prefix=rev_prefix):
                batch.delete(key, column_family=self.db.get_cf_handle(self.REVERSE_CF)) 