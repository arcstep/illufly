import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from illufly.io.huang_index.index import IndexableRocksDB, IndexManager

from datetime import datetime, timezone
import logging

# 只为特定模块设置日志级别
logging.getLogger(__name__).setLevel(logging.INFO)
logger = logging.getLogger(__name__)

class TestFormatIndexValue:
    def test_numeric_format(self):
        """测试数值格式化的各种情况"""
        test_cases = [
            # (输入值, 期望的格式化结果, 说明)
            (0, "c0000000000_000000", "零值"),
            
            # 正数测试
            (1000, "c0000001000_000000", "正整数"),
            (1.5, "c0000000001_500000", "正小数"),
            (0.0001, "c0000000000_000100", "小正数"),
            (123.456789, "c0000000123_456789", "精确到6位小数"),
            
            # 负数测试
            (-1000, "b9999998999_999999", "负整数"),
            (-1.5, "b9999999998_499999", "负小数"),
            (-0.0001, "b9999999999_999899", "小负数"),
            (-123.456789, "b9999999876_543210", "负数精确到6位小数"),
            
            # 特殊值测试
            (float('inf'), "d", "正无穷"),
            (float('-inf'), "a", "负无穷"),
            (float('nan'), "e", "非数值"),
            
            # 边界测试
            (0.00000001, "c0000000000_000000", "超出边界的正数精度"),
            (0.000001, "c0000000000_000001", "最小正数精度"),
            (-0.000001, "b9999999999_999998", "最小负数精度"),
            (-0.00000001, "b9999999999_999999", "超出边界的负数精度"),
            (9999999999, "c9999999999_000000", "最大正整数"),
            (-9999999999, "b0000000000_999999", "最小负整数"),
        ]
        
        for value, expected, desc in test_cases:
            result = IndexManager.format_index_value(value)
            assert result == expected, \
                f"测试失败 - {desc}:\n" \
                f"输入: {value}\n" \
                f"期望: {expected}\n" \
                f"实际: {result}"
            
            # 验证格式的一致性
            if isinstance(value, (int, float)) and value == value:  # 排除 NaN
                # 确保相同的输入总是产生相同的输出
                assert IndexManager.format_index_value(value) == \
                    IndexManager.format_index_value(float(value)), \
                    f"格式不一致 - {desc}: {value}"
                
                # 对于非极值，验证格式长度
                if value not in (float('inf'), float('-inf')):
                    assert len(result) == 18, \
                        f"格式长度错误 - {desc}: {result}"
                    
                    # 验证格式结构
                    assert result[0] in ('b', 'c'), \
                        f"前缀错误 - {desc}: {result}"
                    assert result[11] == '_', \
                        f"分隔符错误 - {desc}: {result}"
                    assert result[1:11].isdigit() and result[13:].isdigit(), \
                        f"数字格式错误 - {desc}: {result}"    

class TestIndexableRocksDB:
    @pytest.fixture
    def db_path(self):
        """创建临时数据库目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def db(self, db_path):
        """创建可索引数据库实例"""
        db = IndexableRocksDB(db_path, logger=logger)  # 集合已在初始化时创建
        yield db
        db.close()
        
    @pytest.fixture
    def indexed_db(self, db):
        """创建带索引配置的数据库实例"""
        # 需要补充注册所有测试中用到的索引
        db.register_model_index(dict, "{email}")
        db.register_model_index(dict, "{age}")
        db.register_model_index(dict, "{vip}")
        db.register_model_index(dict, "{score}")
        db.register_model_index(dict, "{name}")
        db.register_model_index(dict, "{description}")
        db.register_model_index(dict, "{code}")
        db.register_model_index(dict, "{active}")
        db.register_model_index(dict, "{created_at}")
        db.register_model_index(dict, "{updated_at}")
        return db

    def test_index_registration(self, db):
        """测试索引注册"""
        # 先注册索引
        db.register_model_index(dict, "{email}")
        
        # 然后验证索引配置
        assert "{email}" in db.index_manager._model_indexes[dict]

    def test_key_validation(self, indexed_db):
        """测试键验证"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试包含 :key: 的键
        with pytest.raises(ValueError, match=r".*包含保留的关键标识符.*"):
            db.set("users", "user:key:1", {
                "name": "test",
                "email": "test@example.com"
            })
        
        # 测试其他包含冒号的键是允许的
        db.set("users", "user:with:colon", {
            "name": "test",
            "email": "test@example.com"
        })
        
        # 测试值中包含冒号是允许的
        db.set("users", "user:1", {
            "name": "test:with:colon",
            "email": "test:example:com"
        }) 

    def test_base_crud_operations(self, db):
        """测试基本的CRUD操作是否正常"""
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }

        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 创建
        db.set("users", "user:1", user)
        
        # 读取
        saved_user = db.get("users", "user:1")
        assert saved_user == user
        
        # 更新
        user["age"] = 31
        db.set("users", "user:1", user)
        updated_user = db.get("users", "user:1")
        assert updated_user["age"] == 31
        
        # 删除
        db.delete("users", "user:1")
        assert db.get("users", "user:1") is None

    def test_index_auto_update(self, indexed_db):
        """测试索引自动更新"""
        db = indexed_db
        collection = "users"
        key = "user:1"
        
        # 准备测试数据
        user = {
            "name": "张三",
            "email": "zhangsan@example.com",
            "age": 30,
            "vip": True
        }
        
        # 预期的索引格式
        def make_expected_indexes(email, age, vip):
            """生成预期的索引格式"""
            # 格式化数值为10位字符串
            formatted_age = f"{int(age):010d}"  # 整数补零到10位
            formatted_vip = str(vip)  # 布尔值转为 "True" 或 "False"
            
            email_formatted = IndexManager.format_index_value(email)
            age_formatted = IndexManager.format_index_value(age)
            vip_formatted = IndexManager.format_index_value(vip)
            
            indexes = [
                f"idx:users:{{email}}:{email_formatted}:key:user:1",
                f"idx:users:{{age}}:{age_formatted}:key:user:1",
                f"idx:users:{{vip}}:{vip_formatted}:key:user:1"
            ]
            reverse_indexes = [
                f"rev:users:{{email}}:{email_formatted}:idx:users:{{email}}:{email_formatted}:key:user:1",
                f"rev:users:{{age}}:{age_formatted}:idx:users:{{age}}:{age_formatted}:key:user:1",
                f"rev:users:{{vip}}:{vip_formatted}:idx:users:{{vip}}:{vip_formatted}:key:user:1"
            ]
            return indexes, reverse_indexes
        
        db.set_collection_options(collection, {"compression_type": "lz4"})
        
        # 1. 创建记录并验证索引
        db.set(collection, key, user)
        initial_indexes, initial_reverse_indexes = make_expected_indexes("zhangsan@example.com", 30, True)
        
        # 验证索引创建
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"创建后的正向索引: {all_indexes}")
        logger.info(f"创建后的反向索引: {all_reverse_indexes}")
        
        for idx in initial_indexes:
            assert idx in all_indexes, f"索引未创建: {idx}"
        for rev_idx in initial_reverse_indexes:
            assert rev_idx in all_reverse_indexes, f"反向索引未创建: {rev_idx}"
        
        # 2. 更新记录
        user["email"] = "zhangsan_new@example.com"
        user["age"] = 31
        db.set(collection, key, user)
        
        # 新的预期索引
        updated_indexes, updated_reverse_indexes = make_expected_indexes("zhangsan_new@example.com", 31, True)
        
        # 验证索引更新
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"更新后的正向索引: {all_indexes}")
        logger.info(f"更新后的反向索引: {all_reverse_indexes}")
        
        # 验证旧索引已删除
        for idx in initial_indexes:
            if idx not in updated_indexes:  # 只检查应该被删除的索引
                assert idx not in all_indexes, f"旧索引未删除: {idx}"
        
        # 验证新索引已创建
        for idx in updated_indexes:
            assert idx in all_indexes, f"新索引未创建: {idx}"
        for rev_idx in updated_reverse_indexes:
            assert rev_idx in all_reverse_indexes, f"新反向索引未创建: {rev_idx}"
        
        # 3. 删除记录
        db.delete(collection, key)
        
        # 验证索引清理
        all_indexes = list(db.all_indexes(collection))
        all_reverse_indexes = list(db.all_reverse_indexes(collection))
        logger.info(f"删除后的正向索引: {all_indexes}")
        logger.info(f"删除后的反向索引: {all_reverse_indexes}")
        
        for idx in updated_indexes:
            assert idx not in all_indexes, f"索引未被清理: {idx}"
        for rev_idx in updated_reverse_indexes:
            assert rev_idx not in all_reverse_indexes, f"反向索引未被清理: {rev_idx}"

    def test_index_query(self, indexed_db):
        """测试索引查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备测试数据
        users = [
            {"name": "张三", "email": "zhangsan@example.com", "age": 30, "vip": True},
            {"name": "李四", "email": "lisi@example.com", "age": 25, "vip": False},
            {"name": "王五", "email": "wangwu@example.com", "age": 35, "vip": True}
        ]
        
        # 先打印已注册的索引
        logger.info(f"已注册的索引: {db.index_manager._model_indexes}")
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
            
        # 打印创建的索引
        logger.info(f"正向索引: {list(db.all_indexes('users'))}")
        logger.info(f"反向索引: {list(db.all_reverse_indexes('users'))}")
        
        # 测试精确查询 - 使用花括号
        results = list(db.all("users", field_path="{email}", field_value="zhangsan@example.com"))
        assert len(results) == 1, f"email 查询结果: {results}"
        assert results[0][1]["name"] == "张三"
        
        # 测试范围查询 - 使用花括号
        results = list(db.all("users", field_path="{age}", field_value=30))
        assert len(results) == 1, f"age 查询结果: {results}"
        assert results[0][1]["name"] == "张三"
        
        # 测试布尔值查询 - 使用花括号
        results = list(db.all("users", field_path="{vip}", field_value=True))
        assert len(results) == 2, f"vip 查询结果: {results}"
        assert {r[1]["name"] for r in results} == {"张三", "王五"}
        
        # 测试 first/last - 使用花括号
        first_vip = db.first("users", field_path="{vip}", field_value=True)
        assert first_vip[1]["name"] == "张三", f"first_vip 结果: {first_vip}"
        
        last_vip = db.last("users", field_path="{vip}", field_value=True)
        assert last_vip[1]["name"] == "王五", f"last_vip 结果: {last_vip}"

    def test_numeric_index_format(self, indexed_db):
        """测试数值类型的索引格式"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试整数
        db.set("users", "user:1", {"score": 12345})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 1
        assert "idx:users:{score}:c0000012345_000000:key:user:1" in indexes
        
        # 测试负数
        db.set("users", "user:2", {"score": -12345})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 2
        assert "idx:users:{score}:b9999987654_999999:key:user:2" in indexes
        
        # 测试浮点数
        db.set("users", "user:3", {"score": 123.456789})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 3
        assert "idx:users:{score}:c0000000123_456789:key:user:3" in indexes
        
        # 测试小数
        db.set("users", "user:4", {"score": 0.0415})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 4
        assert "idx:users:{score}:c0000000000_041500:key:user:4" in indexes
        
        # 测试科学计数
        db.set("users", "user:5", {"score": 1.23e-4})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 5
        assert "idx:users:{score}:c0000000000_000123:key:user:5" in indexes
        
        # 测试极值
        db.set("users", "user:6", {"score": float('inf')})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 6
        assert "idx:users:{score}:d:key:user:6" in indexes
        
        db.set("users", "user:7", {"score": float('-inf')})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 7
        assert "idx:users:{score}:a:key:user:7" in indexes
        
        db.set("users", "user:8", {"score": float('nan')})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 8
        assert "idx:users:{score}:e:key:user:8" in indexes
        
        # 测试零值
        db.set("users", "user:9", {"score": 0})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 9
        assert "idx:users:{score}:c0000000000_000000:key:user:9" in indexes

    def test_numeric_range_query(self, indexed_db):
        """测试数值类型的范围查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备测试数据
        test_values = [
            0, -1.5, 1.5, 1000, -1000, 0.0001,
            -0.0001, 11, 12, 10000, 0.000001,
        ]
        for i, value in enumerate(test_values):
            db.set("users", f"user:{i}", {"score": value})
        
        # 获取所有索引并排序
        indexes = sorted(db.all_indexes("users"))
        logger.info(f"所有索引: {indexes}")
        
        # 验证索引的字典序
        expected_index_order = [
            "idx:users:{score}:c0000000000_000000:key:user:0",  # 0
            "idx:users:{score}:b9999999998_499999:key:user:1",  # -1.5
            "idx:users:{score}:c0000000001_500000:key:user:2",  # 1.5
            "idx:users:{score}:c0000001000_000000:key:user:3",  # 1000
            "idx:users:{score}:b9999998999_999999:key:user:4",  # -1000
            "idx:users:{score}:c0000000000_000100:key:user:5",  # 0.0001
            "idx:users:{score}:b9999999999_999899:key:user:6",  # -0.0001
            "idx:users:{score}:c0000000011_000000:key:user:7",  # 11
            "idx:users:{score}:c0000000012_000000:key:user:8",  # 12
            "idx:users:{score}:c0000010000_000000:key:user:9",  # 10000
            "idx:users:{score}:c0000000000_000001:key:user:10",  # 0.000001
        ]
        assert sorted(indexes) == sorted(expected_index_order)
        
        # 测试部分范围查询
        results = list(db.all("users", field_path="{score}", 
                             start=10, 
                             end=20))
        scores = [r[1]["score"] for r in results]
        expected_subset = [11, 12]
        logger.info(f"[10, 20] 范围查询结果: {scores}")
        assert sorted(scores) == sorted(expected_subset)  # 只验证结果集合是否相同

        # 测试部分范围查询
        results = list(db.all("users", field_path="{score}", 
                             start=-1, 
                             end=1))
        scores = [r[1]["score"] for r in results]
        expected_subset = [-0.0001, 0, 0.0001, 0.000001]
        logger.info(f"[-1, 0] 范围查询结果: {scores}")
        assert sorted(scores) == sorted(expected_subset)  # 只验证结果集合是否相同

        # 测试范围查询结果
        results = list(db.all("users", field_path="{score}", 
                             start=float('-inf'), 
                             end=float('inf')))
        scores = [r[1]["score"] for r in results]
        logger.info(f"[-inf, inf] 范围查询结果: {scores}")
        assert sorted(scores) == sorted(test_values)  # 只验证结果集合是否相同
        
    def test_boolean_index_format(self, indexed_db):
        """测试布尔值的索引格式"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试 True
        db.set("users", "user:1", {"active": True})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 1
        assert "idx:users:{active}:true:key:user:1" in indexes
        
        # 测试 False
        db.set("users", "user:2", {"active": False})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 2
        assert "idx:users:{active}:false:key:user:2" in indexes

    def test_string_index_format(self, indexed_db):
        """测试字符串的索引格式"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试短字符串
        short_str = "hello world"
        db.set("users", "user:1", {"name": short_str})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 1
        assert f"idx:users:{{name}}:s{short_str}:key:user:1" in indexes
        
        # 测试长字符串
        long_str = "x" * 200
        db.set("users", "user:2", {"description": long_str})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 2
        assert any(idx.startswith("idx:users:{description}:h") for idx in indexes)
        
        # 测试空字符串
        db.set("users", "user:3", {"name": ""})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 3
        assert "idx:users:{name}:empty:key:user:3" in indexes
        
        # 测试 Unicode 字符
        db.set("users", "user:4", {"name": "张三"})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 4
        assert "idx:users:{name}:s张三:key:user:4" in indexes

    def test_datetime_index_format(self, indexed_db):
        """测试日期时间的索引格式"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试不带微秒的时间
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        db.set("users", "user:1", {"created_at": dt})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 1
        assert "idx:users:{created_at}:t1672574400:key:user:1" in indexes
        
        # 测试带微秒的时间
        dt = datetime(2023, 1, 1, 12, 0, 0, 123456, tzinfo=timezone.utc)
        db.set("users", "user:2", {"updated_at": dt})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 2
        assert "idx:users:{updated_at}:t1672574400:key:user:2" in indexes

    def test_range_query_with_formatted_index(self, indexed_db):
        """测试使用格式化索引的范围查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备数据
        users = [
            {"score": 123.456, "created_at": datetime(2023, 1, 1, tzinfo=timezone.utc)},
            {"score": -456.789, "created_at": datetime(2023, 1, 2, tzinfo=timezone.utc)},
            {"score": 789.123, "created_at": datetime(2023, 1, 3, tzinfo=timezone.utc)},
            {"score": 1000.0, "created_at": datetime(2023, 1, 4, tzinfo=timezone.utc)},
        ]
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
        
        # 测试数值范围查询
        results = list(db.all("users", field_path="{score}", start=0, end=800))
        assert len(results) == 2
        
        # 测试时间范围查询
        results = list(db.all("users", 
                             field_path="{created_at}", 
                             start=datetime(2023, 1, 2, tzinfo=timezone.utc)))
        assert len(results) == 3 

        results = list(db.all("users", 
                             field_path="{created_at}", 
                             end=datetime(2023, 1, 2, tzinfo=timezone.utc)))
        assert len(results) == 1

    def test_null_index_format(self, indexed_db):
        """测试空值的索引格式"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 测试 None 值
        db.set("users", "user:1", {"score": None})
        indexes = list(db.all_indexes("users"))
        assert len(indexes) == 1
        assert "idx:users:{score}:null:key:user:1" in indexes

    def test_range_query(self, indexed_db):
        """测试范围查询"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 准备测试数据
        users = [
            {"name": "张三", "email": "zhangsan@example.com", "age": 30, "score": 85.5},
            {"name": "李四", "email": "lisi@example.com", "age": 25, "score": 92.0},
            {"name": "王五", "email": "wangwu@example.com", "age": 35, "score": 78.5},
            {"name": "赵六", "email": "zhaoliu@example.com", "age": 28, "score": 88.0},
            {"name": "钱七", "email": "qianqi@example.com", "age": 32, "score": 95.5}
        ]
        
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
        
        # 测试年龄范围查询
        results = list(db.all("users", field_path="{age}", start=28, end=32))
        assert len(results) == 3, f"age 范围查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"张三", "赵六", "钱七"}, f"查询到的用户: {names}"
        
        # 测试分数范围查询（浮点数）
        results = list(db.all("users", field_path="{score}", start=85.0, end=93.0))
        assert len(results) == 3, f"score 范围查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"张三", "李四", "赵六"}, f"查询到的用户: {names}"
        
        # 测试只有起始值的范围查询
        results = list(db.all("users", field_path="{age}", start=32))
        assert len(results) == 2, f"age >= 32 查询结果: {results}"
        names = {r[1]["name"] for r in results}
        assert names == {"王五", "钱七"}, f"查询到的用户: {names}"
        
        # 测试只有结束值的范围查询
        results = list(db.all("users", field_path="{score}", end=80.0))
        assert len(results) == 1, f"score <= 80.0 查询结果: {results}"
        assert results[0][1]["name"] == "王五"
        
        # 测试范围查询的排序
        results = list(db.all("users", field_path="{age}", start=25, end=35))
        ages = [r[1]["age"] for r in results]
        assert ages == sorted(ages), f"年龄排序不正确: {ages}"
        
        # 测试反向范围查询
        results = list(db.all("users", field_path="{age}", start=25, end=35, reverse=True))
        ages = [r[1]["age"] for r in results]
        assert ages == sorted(ages, reverse=True), f"反向年龄排序不正确: {ages}"
        
        # 测试 first/last 与范围查询结合
        first_result = db.first("users", field_path="{age}", start=28, end=32)
        assert first_result[1]["age"] == 28, f"范围内第一个结果不正确: {first_result}"
        
        last_result = db.last("users", field_path="{age}", start=28, end=32)
        assert last_result[1]["age"] == 32, f"范围内最后一个结果不正确: {last_result}" 

    def test_index_rebuild(self, indexed_db):
        """测试索引重建功能"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 1. 先写入一些数据
        users = [
            {"name": "张三", "age": 30},
            {"name": "李四", "age": 25}
        ]
        for i, user in enumerate(users, 1):
            db.set("users", f"user:{i}", user)
        
        # 2. 注册新的索引
        db.register_model_index(dict, "{score}")
        
        # 3. 添加带新索引字段的数据
        db.set("users", "user:3", {"name": "王五", "age": 35, "score": 95})
        
        # 4. 重建索引
        db.rebuild_indexes("users")
        
        # 5. 验证所有索引都正确重建
        # 验证 name 索引
        results = list(db.all("users", field_path="{name}", field_value="王五"))
        assert len(results) == 3
        
        # 验证 age 索引
        results = list(db.all("users", field_path="{age}", start=25, end=35))
        assert len(results) == 3
        
        # 验证新增的 score 索引
        results = list(db.all("users", field_path="{score}", field_value=95))
        assert len(results) == 1
        assert results[0][1]["score"] == 95

    def test_query_without_conditions(self, indexed_db):
        """测试没有提供查询条件时的错误处理"""
        db = indexed_db
        db.set_collection_options("users", {"compression_type": "lz4"})
        
        # 注册索引并添加测试数据
        db.register_model_index(dict, "{age}")
        db.set("users", "user:1", {"age": 30})
        
        # 测试没有提供任何查询条件
        with pytest.raises(ValueError) as exc_info:
            list(db.all("users", field_path="{age}"))
        assert "必须提供查询条件" in str(exc_info.value)
        
        # 验证正确的查询方式
        # 精确匹配
        results = list(db.all("users", field_path="{age}", value=30))
        assert len(results) == 1
        
        # 范围查询 - 只有起始值
        results = list(db.all("users", field_path="{age}", start=25))
        assert len(results) == 1
        
        # 范围查询 - 只有结束值
        results = list(db.all("users", field_path="{age}", end=35))
        assert len(results) == 1
        
        # 范围查询 - 同时提供起始值和结束值
        results = list(db.all("users", field_path="{age}", start=25, end=35))
        assert len(results) == 1

