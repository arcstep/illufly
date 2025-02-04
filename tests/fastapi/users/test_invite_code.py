import pytest
from pathlib import Path
from datetime import datetime, timedelta
from illufly.fastapi.users import InviteCodeManager
from illufly.fastapi.users.invite import InviteCode

@pytest.fixture
def invite_code_manager():
    return InviteCodeManager()

def test_generate_invite_codes(invite_code_manager):
    """测试批量生成邀请码
    验证点:
    - 验证生成的邀请码数量是否正确
    - 验证生成的每个邀请码是否为InviteCode实例
    - 验证生成的每个邀请码是否未被使用
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(3, owner_id)
    
    assert len(codes) == 3
    assert all(isinstance(code, InviteCode) for code in codes)
    assert all(not code.is_used() for code in codes)

def test_get_all_invite_codes(invite_code_manager):
    """测试获取所有邀请码
    验证点:
    - 验证获取到的邀请码数量是否正确
    - 验证获取到的邀请码是否与生成的邀请码一致
    """
    owner_id = "test_user"
    generated_codes = invite_code_manager.generate_new_invite_codes(2, owner_id)
    stored_codes = invite_code_manager.get_invite_codes(owner_id)
    
    assert len(stored_codes) == 2
    assert all(code.invite_code in [c.invite_code for c in generated_codes] for code in stored_codes)

def test_use_valid_invite_code(invite_code_manager):
    """测试使用有效邀请码
    验证点:
    - 验证使用邀请码的结果是否为True
    - 验证邀请码的使用状态是否更新
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(1, owner_id)
    code = codes[0]
    
    assert invite_code_manager.use_invite_code(code.invite_code, owner_id)
    assert code.is_used()

def test_use_expired_invite_code(invite_code_manager):
    """测试使用过期邀请码
    验证点:
    - 验证使用过期邀请码的结果是否为False
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(1, owner_id)
    code = codes[0]
    
    # 修改过期时间为过去的时间
    code.expired_at = datetime.now() - timedelta(days=1)
    # 保存修改后的状态
    invite_code_manager._storage.set([code], owner_id)
    
    assert not invite_code_manager.use_invite_code(code.invite_code, owner_id)

def test_use_nonexistent_invite_code(invite_code_manager):
    """测试使用不存在的邀请码
    验证点:
    - 验证使用不存在的邀请码的结果是否为False
    """
    owner_id = "test_user"
    assert not invite_code_manager.use_invite_code("nonexistent_code", owner_id)

def test_is_valid_invite_code(invite_code_manager):
    """测试验证码合法性检查
    验证点:
    - 验证有效邀请码的合法性检查结果是否为True
    - 验证无效邀请码的合法性检查结果是否为False
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(1, owner_id)
    code = codes[0]
    
    assert invite_code_manager.invite_code_is_valid(code.invite_code, owner_id)
    assert not invite_code_manager.invite_code_is_valid("invalid_code", owner_id)

# 建议添加的新功能测试
def test_delete_invite_code(invite_code_manager):
    """测试删除特定邀请码
    验证点:
    - 验证删除后剩余的邀请码数量是否正确
    - 验证删除后剩余的邀请码中不包含被删除的邀请码
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(2, owner_id)
    code_to_delete = codes[0].invite_code
    
    invite_code_manager.delete_invite_code(code_to_delete, owner_id)
    remaining_codes = invite_code_manager.get_invite_codes(owner_id)
    
    assert len(remaining_codes) == 1
    assert all(code.invite_code != code_to_delete for code in remaining_codes)

def test_cleanup_expired_codes(invite_code_manager):
    """测试清理过期邀请码
    验证点:
    - 验证清理过期邀请码的数量是否正确
    - 验证清理后剩余的邀请码数量是否正确
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(3, owner_id)
    
    # 修改两个码的过期时间
    codes[0].expired_at = datetime.now() - timedelta(days=1)
    codes[1].expired_at = datetime.now() - timedelta(days=1)
    # 保存修改后的状态
    invite_code_manager._storage.set(codes, owner_id)
    
    deleted_count = invite_code_manager.cleanup_expired_codes(owner_id)
    remaining_codes = invite_code_manager.get_invite_codes(owner_id)
    
    assert deleted_count == 2
    assert len(remaining_codes) == 1

def test_get_usage_statistics(invite_code_manager):
    """测试获取使用统计
    验证点:
    - 验证总邀请码数量是否正确
    - 验证已使用邀请码数量是否正确
    - 验证过期邀请码数量是否正确
    - 验证可用邀请码数量是否正确
    """
    owner_id = "test_user"
    codes = invite_code_manager.generate_new_invite_codes(3, owner_id)
    
    # 使用一个码，让一个码过期
    invite_code_manager.use_invite_code(codes[0].invite_code, owner_id)
    codes[1].expired_at = datetime.now() - timedelta(days=1)
    # 保存修改后的状态
    invite_code_manager._storage.set(codes, owner_id)
    
    stats = invite_code_manager.get_usage_statistics(owner_id)
    
    assert stats["total"] == 3
    assert stats["used"] == 1
    assert stats["expired"] == 1
    assert stats["available"] == 1