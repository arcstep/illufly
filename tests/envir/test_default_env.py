import pytest
from unittest.mock import patch
from illufly.envir.default_env import get_env

def test_get_env_with_default():
    """测试获取默认环境变量值"""
    # 测试一个不存在的环境变量，应该返回默认值
    assert get_env('ILLUFLY_TEMP_DIR').endswith('__ILLUFLY__')
    assert get_env('ILLUFLY_DOCS') == '__DOCS__'

def test_get_env_with_override():
    """测试环境变量覆盖默认值"""
    test_value = '/custom/path'
    with patch.dict('os.environ', {'ILLUFLY_DOCS': test_value}):
        assert get_env('ILLUFLY_DOCS') == test_value

def test_get_env_invalid_key():
    """测试无效的环境变量键"""
    with pytest.raises(ValueError) as exc_info:
        get_env('INVALID_KEY')
    assert "Not Exist" in str(exc_info.value)

def test_get_env_all_defaults():
    """测试获取所有默认值"""
    defaults = get_env()
    # 验证一些关键配置是否存在
    assert 'ILLUFLY_DOCS' in defaults
    assert 'ILLUFLY_TEMP_DIR' in defaults
    assert isinstance(defaults, dict) 