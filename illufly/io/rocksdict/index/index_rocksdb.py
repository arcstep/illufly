from typing import Type, Any, Optional, Dict, List, get_origin, Union, Iterator, Set
from pydantic import BaseModel
from rocksdict import Options, Rdict, WriteBatch, DBCompressionType

from ..base_rocksdb import BaseRocksDB
from .accessor import AccessorRegistry
from .path_parser import PathParser
from datetime import datetime

import hashlib
import base64

class IndexedRocksDB(BaseRocksDB):
    """
    支持针对一个模型的多种索引路径管理。

    在增加、删除、修改对象时根据注册的索引路径自动更新索引。
    """

    def __init__(self, path: str, options: Optional[Options] = None, logger=None):
        super().__init__(path, options, logger)

        # 创建索引元数据的列族
        all_cfs = self.list_column_families(path)
        if self.INDEX_METADATA_CF not in all_cfs:
            self.create_column_family(self.INDEX_METADATA_CF, options=self._get_indexes_cf_options())
        if self.INDEX_CF not in all_cfs:
            self.create_column_family(self.INDEX_CF, options=self._get_indexes_cf_options())

    INDEX_METADATA_CF = "indexes_metadata"  # 索引元数据列族
    INDEX_CF = "indexes"      # 索引列族

    # 模型前缀
    MODEL_PREFIX_FORMAT = "idx:{cf_name}:{model_name}"

    # 索引元数据格式
    INDEX_METADATA_FORMAT = MODEL_PREFIX_FORMAT + ":{field_path}"

    # 索引格式
    INDEX_KEY_FORMAT = INDEX_METADATA_FORMAT + ":{value}:key:{key}"

    # 关键标识符
    RESERVED_WORD_IN_INDEX = ":key:"
    RESERVED_WORD_IN_REVERSE = ":rev:"

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
    
    _accessor_registry = AccessorRegistry()
    _path_parser = PathParser()

    @classmethod
    def _get_indexes_cf_options(cls) -> Options:
        """
        获取专门为索引列族优化的rocksdb列族配置
        """
        options = Options()
        options.set_write_buffer_size(64 * 1024 * 1024)  # 64MB
        options.set_max_write_buffer_number(4)  # 允许更多的写缓冲
        options.set_min_write_buffer_number_to_merge(1)  # 尽快刷新到L0
        options.set_target_file_size_base(64 * 1024 * 1024)  # 64MB
        options.set_compression_type(DBCompressionType.none())  # 禁用压缩，因为索引值都是None
        options.set_bloom_locality(1)  # 优化布隆过滤器的局部性
        return options

    @classmethod
    def _get_base_type(cls, model_class: Type) -> Type:
        """获取基础类型"""
        
        # 处理 typing 类型
        if hasattr(model_class, '__origin__'):
            return model_class.__origin__
            
        # 处理内置类型
        if model_class in (dict, Dict):
            return dict
            
        # 其他类型保持不变
        return model_class

    @classmethod
    def _validate_key(cls, key: str) -> None:
        if cls.RESERVED_WORD_IN_INDEX in key:
            raise ValueError(
                f"键 '{key}' 包含保留的关键标识符 '{cls.RESERVED_WORD_IN_INDEX}'。"
                "这个词用于索引解析，不能在键中使用。"
            )

    @classmethod
    def _validate_value(cls, value: str) -> None:
        if cls.RESERVED_WORD_IN_REVERSE in value:
            raise ValueError(
                f"值 '{value}' 包含保留的关键标识符 '{cls.RESERVED_WORD_IN_REVERSE}'。"
                "这个词列用于索引解析，不能在值中使用。"
            )

    @classmethod
    def _escape_special_chars(cls, value: str) -> str:
        """替换字符串中的特殊字符，使用Base64编码"""
        result = value
        for char in cls.SPECIAL_CHARS:
            # 将特殊字符转换为Base64编码
            encoded = base64.b64encode(char.encode()).decode()
            result = result.replace(char, encoded)
        return result

    @classmethod
    def _fetch_key_from_index(cls, index_key: str) -> str:
        """从索引中获取键"""
        parts = index_key.rsplit(cls.RESERVED_WORD_IN_INDEX, 1)
        if len(parts) != 2:
            raise ValueError(f"从索引键 {index_key} 中提取键失败")
        return parts[1]

    @classmethod
    def _fetch_field_path_from_index(cls, index_key: str) -> str:
        """从索引中获取字段路径"""
        parts = index_key.rsplit(":", 1)
        if len(parts) != 2:
            raise ValueError(f"从索引键 {index_key} 中提取字段路径失败")
        return parts[1]

    @classmethod
    def format_index_value(cls, value: Any) -> str:
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

    @property
    def indexes_metadata_cf(self) -> Rdict:
        return self.get_column_family(self.INDEX_METADATA_CF)

    @property
    def indexes_cf(self) -> Rdict:
        return self.get_column_family(self.INDEX_CF)

    def register_indexes(self, model_name: str, model_class: Type, field_path: str, cf_name: str=None):
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

        # 注册索引元数据
        base_type = self._get_base_type(model_class)

        cf_name = cf_name or self.default_cf_name
        key = self.INDEX_METADATA_FORMAT.format(
            cf_name=cf_name,
            model_name=model_name,
            field_path=field_path
        )
        self.indexes_metadata_cf[key] = base_type

        self._logger.info(f"注册索引元数据: {key} -> {cf_name}.{model_name}#{field_path}")

    def _make_index_key(self, model_name: str, field_path: str, field_value: Any, key: str, cf_name: str=None) -> str:
        """创建索引键"""
        key = self._escape_special_chars(key)
        self._validate_key(key)
        formatted_value = self.format_index_value(field_value)
        self._validate_value(formatted_value)
        cf_name = cf_name or self.default_cf_name
        return self.INDEX_KEY_FORMAT.format(
            cf_name=cf_name,
            model_name=model_name,
            field_path=field_path,
            value=formatted_value,
            key=key
        )
    
    def update_with_indexes(self, model_name: str, key: str, new_value: Any, cf_name: str=None):
        """更新键值，并自动更新索引"""
        self._logger.info(f"开始更新索引: model_name={model_name}, key={key}, new_value={new_value}, cf_name={cf_name}")

        cf_name = cf_name or self.default_cf_name
        cf = self.get_column_family(cf_name)
        cf_handle = self.get_column_family_handle(cf_name)

        key_not_exist = self.not_exist(key, rdict=cf)
        if not key_not_exist:
            old_value = self.get(key, rdict=cf)
        else:
            old_value = None

        # 获取对象所有路径
        model_prefix = self.MODEL_PREFIX_FORMAT.format(cf_name=cf_name, model_name=model_name)

        all_paths = self.keys(prefix=model_prefix, rdict=self.indexes_metadata_cf)

        if not all_paths:
            cf.put(key, new_value, cf_handle)
            self._logger.info(f"值已更新，但没有索引注册")
            return

        # 处理删除操作
        batch = WriteBatch()

        # 更新值
        batch.put(key, new_value, cf_handle)

        # 处理对象所有属性访问路径的索引
        indexes_cf_handle = self.get_column_family_handle(self.INDEX_CF)
        for path in all_paths:
            field_path = self._fetch_field_path_from_index(path)
            if not key_not_exist:
                field_value = self._accessor_registry.get_field_value(old_value, field_path)
                old_index = self._make_index_key(
                    model_name=model_name,
                    field_path=field_path,
                    field_value=field_value,
                    key=key,
                    cf_name=cf_name
                )
                batch.delete(old_index, indexes_cf_handle)
                self._logger.info(f"准备删除旧索引: {old_index}")
            field_value = self._accessor_registry.get_field_value(new_value, field_path)
            new_index = self._make_index_key(
                model_name=model_name,
                field_path=field_path,
                field_value=field_value,
                key=key,
                cf_name=cf_name
            )
            batch.put(new_index, None, indexes_cf_handle)
            self._logger.info(f"准备创建新索引: {new_index}")

        self.write(batch)
        self._logger.info(f"批处理任务提交完成，值和索引已更新")

    def delete_with_indexes(self, model_name: str, key: str, cf_name: str=None):
        """删除键值，并自动删除索引"""
        self._logger.info(f"开始删除索引: model_name={model_name}, key={key}, cf_name={cf_name}")

        cf_name = cf_name or self.default_cf_name
        cf = self.get_column_family(cf_name)
        key_not_exist = self.not_exist(key, rdict=cf)
        if key_not_exist:
            self._logger.info(f"不存在旧值，无需删除")
            return

        old_value = self.get(key, rdict=cf)

        # 处理删除操作
        batch = WriteBatch()

        # 更新值
        cf_handle = self.get_column_family_handle(cf_name)
        batch.delete(key, cf_handle)

        # 获取对象所有路径
        model_prefix = self.MODEL_PREFIX_FORMAT.format(cf_name=cf_name, model_name=model_name)

        all_paths = self.keys(prefix=model_prefix, rdict=self.indexes_metadata_cf)

        if not all_paths:
            self.write(batch)
            self._logger.info(f"批处理任务提交完成，值已删除，但没有索引注册")
            return

        # 处理对象所有属性访问路径的索引
        indexes_cf_handle = self.get_column_family_handle(self.INDEX_CF)
        for path in all_paths:
            field_path = self._fetch_field_path_from_index(path)
            field_value = self._accessor_registry.get_field_value(old_value, field_path)
            old_index = self._make_index_key(
                model_name=model_name,
                field_path=field_path,
                field_value=field_value,
                key=key,
                cf_name=cf_name
            )
            batch.delete(old_index, indexes_cf_handle)
            self._logger.info(f"准备删除索引: {old_index}")

        self.write(batch)
        self._logger.info(f"批处理任务提交完成，值和索引已删除")        

    def iter_keys_with_indexes(
        self,
        model_name: str,
        field_path: str,
        field_value: Any = None, 
        start: Optional[Any] = None,
        end: Optional[Any] = None,
        limit: Optional[int] = None,
        reverse: bool = False,
        cf_name: str = None,
    ) -> Iterator[str]:
        """通过索引查询键"""
        index_cf = self.get_column_family(self.INDEX_CF)

        # 验证查询参数
        if field_value is None and start is None and end is None:
            error_msg = (
                f"查询字段 {field_path} 时必须提供查询条件："
                f"\n1. 提供 field_value 参数进行精确匹配"
                f"\n2. 提供 start 和/或 end 参数进行范围查询"
            )
            self._logger.error(error_msg)
            raise ValueError(error_msg)
        
        # 构建基础前缀
        cf_name = cf_name or self.default_cf_name
        model_prefix = self.MODEL_PREFIX_FORMAT.format(cf_name=cf_name, model_name=model_name)
        
        if start is not None or end is not None:
            # 范围查询时，确保只查询指定字段的索引
            start_key = self._make_index_key(
                model_name=model_name,
                field_path=field_path,
                field_value=start,
                key="",
                cf_name=cf_name
            )
            end_key = self._make_index_key(
                model_name=model_name,
                field_path=field_path,
                field_value=end,
                key="",
                cf_name=cf_name
            )
            target_key = None
        else:
            start_key = None
            end_key = None
            target_key = self._make_index_key(
                model_name=model_name,
                field_path=field_path,
                field_value=field_value,
                key="",
                cf_name=cf_name
            )

        self._logger.info(f"范围查询: start={start_key}, end={end_key}")
        resp = self.iter_keys(
            prefix=target_key,
            start=start_key,
            end=end_key,
            limit=limit,
            reverse=reverse,
            rdict=index_cf
        )
        for index in resp:
            key = self._fetch_key_from_index(index)
            yield key
    
    def iter_items_with_indexes(self, *args, **kwargs):
        for key in self.iter_keys_with_indexes(*args, **kwargs):
            yield key, self.get(key, rdict=self.indexes_cf)

    def items_with_indexes(self, *args, **kwargs):
        return list(self.iter_items_with_indexes(*args, **kwargs))
