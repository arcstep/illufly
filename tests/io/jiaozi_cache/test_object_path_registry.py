from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pathlib import Path
import pytest
from pydantic import BaseModel
from dataclasses import dataclass
from illufly.io.jiaozi_cache import (
    ObjectPathRegistry,
    PathInfo,
    PathType,
    NotFoundError,
)
import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 测试用的类型定义
class TestObjectPathRegistry:
    """测试对象路径注册表"""
    
    @pytest.fixture
    def registry(self):
        return ObjectPathRegistry()
    
    def test_collect_nested_paths_dict(self, registry):
        """测试字典的嵌套路径收集"""
        test_dict = {
            "name": "test",
            "config": {
                "theme": "dark",
                "settings": {
                    "enabled": True
                }
            },
            "items": [
                {"id": 1, "value": "first"},
                {"id": 2, "value": "second"}
            ]
        }
        
        handler = registry._find_handler(test_dict)
        paths = registry._collect_nested_paths(test_dict, handler)
        
        # 验证路径收集结果
        expected_paths = {
            "",  # 根路径
            "{name}",
            "{config}",
            "{config}{theme}",
            "{config}{settings}",
            "{config}{settings}{enabled}",
            "{items}",
            "{items}[*]",
            "{items}[*]{id}",
            "{items}[*]{value}",
        }
        
        # 收集实际路径
        collected_paths = {p.path for p in paths}
        
        # 打印调试信息
        logger.info("预期路径:")
        for p in expected_paths:
            logger.info(f"  {p}")
        
        logger.info("\n实际路径:")
        for p in collected_paths:
            logger.info(f"  {p}")
        
        # 验证每个预期路径都存在
        for expected_path in expected_paths:
            assert any(p.path == expected_path for p in paths), \
                f"未找到预期路径: {expected_path}"
        
        # 验证访问方法
        for path_info in paths:
            if "{" in path_info.path:
                assert path_info.access_method == "bracket", \
                    f"路径 {path_info.path} 应使用 bracket 访问"
            elif "[" in path_info.path:
                assert path_info.access_method == "list", \
                    f"路径 {path_info.path} 应使用 list 访问"
            else:
                assert path_info.access_method == "dot", \
                    f"路径 {path_info.path} 应使用 dot 访问"
    
    def test_collect_nested_paths_custom_object(self, registry):
        """测试自定义对象的嵌套路径收集"""
        class Config:
            def __init__(self):
                self.theme = "light"
                self.settings = {"debug": True}
                
        class User:
            def __init__(self):
                self.name = "test"
                self.config = Config()
                self.tags = ["a", "b"]
                
        user = User()
        handler = registry._find_handler(user)
        paths = registry._collect_nested_paths(user, handler)
        
        # 验证路径收集结果
        expected_paths = {
            "",  # 根路径
            "name",
            "config",
            "config.theme",
            "config.settings",
            "config.settings{debug}",
            "tags",
            "tags[*]",
        }
        
        collected_paths = {p.path for p in paths}
        assert collected_paths == expected_paths
        
        # 验证访问方法
        for path_info in paths:
            if "{" in path_info.path:
                assert path_info.access_method == "bracket"
            elif "[" in path_info.path:
                assert path_info.access_method == "list"
            else:
                assert path_info.access_method == "dot"
    
    def test_collect_nested_paths_empty(self, registry):
        """测试空对象的路径收集"""
        empty_dict = {}
        handler = registry._find_handler(empty_dict)
        paths = registry._collect_nested_paths(empty_dict, handler)
        
        # 空字典应该只有根路径
        assert len(paths) == 1
        assert paths[0].path == ""
        
    def test_collect_nested_paths_circular(self, registry):
        """测试循环引用的处理"""
        circular_dict = {}
        circular_dict["self"] = circular_dict
        
        handler = registry._find_handler(circular_dict)
        paths = registry._collect_nested_paths(circular_dict, handler)
        
        # 应该只收集第一层路径，避免无限递归
        expected_paths = {"", "{self}"}
        collected_paths = {p.path for p in paths}
        assert collected_paths == expected_paths
