import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from datetime import datetime
from illufly.fastapi.user import UserManager, User, UserRole
from illufly.fastapi.auth import AuthManager
from illufly.fastapi.common import FileConfigStore

class TestUserManagerInitialization:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        # 设置默认的密码哈希行为
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        # 设置基本存储操作行为
        mock_storage.get.return_value = None
        mock_storage.list_owners.return_value = []
        mock_storage.has_duplicate.return_value = False
        mock_storage.set.return_value = True
        return mock_storage

    def test_init_with_default_storage(self, auth_manager):
        """测试使用默认存储初始化"""
        # 创建一个完整的 Mock FileConfigStore 实例
        mock_file_store = Mock(spec=FileConfigStore)
        
        # 设置所有必需的方法返回值
        mock_file_store.list_owners.return_value = []
        mock_file_store.get.return_value = None
        mock_file_store.has_duplicate.return_value = False
        mock_file_store.set.return_value = None  # set 方法没有返回值
        
        # 创建一个 FileConfigStore 类的 Mock
        mock_store_class = Mock()
        
        # 设置泛型类的行为
        def store_factory(data_class):
            # 验证泛型参数
            assert data_class == User
            # 返回预配置的 mock 实例
            return lambda **kwargs: mock_file_store
        
        mock_store_class.__getitem__ = Mock(side_effect=store_factory)
        
        # Patch FileConfigStore
        with patch('illufly.fastapi.user.manager.FileConfigStore', mock_store_class):
            # 初始化管理器
            manager = UserManager(auth_manager)
            
            # 验证 FileConfigStore 的创建
            mock_store_class.__getitem__.assert_called_once_with(User)
            
            # 验证存储方法的调用
            mock_file_store.list_owners.assert_called()  # 在 get_user_by_username 中调用
            mock_file_store.has_duplicate.assert_called()  # 在 create_user 中调用
            mock_file_store.set.assert_called_once()  # 在创建管理员用户时调用
            
            # 验证管理员用户创建
            call_args = mock_file_store.set.call_args
            print(f">>> call_args: {call_args}")  # 打印调用参数
            assert call_args is not None
            
            # 获取位置参数和关键字参数
            args, kwargs = call_args
            
            # 验证创建的用户
            created_user = args[0]  # 第一个位置参数是 value
            assert isinstance(created_user, User)
            assert created_user.username == 'admin'
            assert created_user.email == 'admin@illufly.com'
            assert UserRole.ADMIN in created_user.roles
            
            # 验证 owner_id
            assert kwargs.get('owner_id') == 'admin'  # owner_id 应在关键字参数中

    def test_init_with_custom_storage(self, auth_manager, storage):
        """测试使用自定义存储初始化
        
        验证:
        1. 自定义存储被正确使用
        2. 管理器被正确初始化
        3. 确保管理员用户被创建
        """
        storage.has_duplicate.return_value = False
        
        # 初始化管理器
        manager = UserManager(auth_manager, storage)
        
        # 验证基本属性
        assert manager.auth_manager == auth_manager
        assert manager._storage == storage
        
        # 验证管理员用户创建
        storage.set.assert_called_once()
        call_args = storage.set.call_args
        
        # 验证创建的用户对象
        created_user = call_args[0][0]  # 第一个位置参数是 User 对象
        assert isinstance(created_user, User)
        assert created_user.user_id == "admin"
        assert created_user.username == "admin"
        assert created_user.email == "admin@illufly.com"
        assert UserRole.ADMIN in created_user.roles
        
        # 验证 owner_id
        assert call_args[1]['owner_id'] == "admin"

    def test_ensure_admin_user_creates_admin(self, auth_manager, storage):
        """测试确保管理员用户存在 - 创建新管理员
        
        验证:
        1. 当管理员不存在时，创建新管理员
        2. 管理员用户具有正确的角色和属性
        """
        # 设置 mock 行为 - 管理员不存在
        storage.get.return_value = None
        storage.list_owners.return_value = []
        storage.has_duplicate.return_value = False
        
        auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "admin_password_hash"
        }
        
        # 初始化管理器（这会触发管理员创建）
        manager = UserManager(auth_manager, storage)
        
        # 验证管理员创建
        storage.set.assert_called_once()
        call_args = storage.set.call_args
        
        # 验证创建的用户对象
        created_user = call_args[0][0]
        assert isinstance(created_user, User)
        assert created_user.user_id == "admin"
        assert created_user.username == "admin"
        assert created_user.password_hash == "admin_password_hash"
        assert UserRole.ADMIN in created_user.roles
        assert UserRole.OPERATOR in created_user.roles
        assert not created_user.require_password_change
        
        # 验证 owner_id
        assert call_args[1]['owner_id'] == "admin"
        
        # 验证管理员ID被添加到管理员集合
        assert "admin" in manager._admin_ids

    def test_ensure_admin_user_exists(self, auth_manager, storage):
        """测试确保管理员用户存在 - 管理员已存在
        
        验证:
        1. 当管理员已存在时，不创建新管理员
        2. 现有管理员的ID被正添加到管理员集合
        """
        # 创建现有管理员用户
        existing_admin = User(
            user_id="admin",
            username="admin",
            email="admin@illufly.com",
            password_hash="existing_hash",
            roles={UserRole.ADMIN, UserRole.OPERATOR},
            created_at=datetime.now(),
            require_password_change=False
        )
        
        # 设置 mock 行为 - 管理员已存在
        storage.get.return_value = existing_admin
        storage.list_owners.return_value = ["admin"]
        storage.has_duplicate.return_value = False
        
        # 初始化管理器
        manager = UserManager(auth_manager, storage)
        
        # 验证没有创建新管理员
        storage.set.assert_not_called()
        
        # 验证管理员ID被添加到管理员集合
        assert "admin" in manager._admin_ids

class TestUserCreationAndVerification:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        # 设置默认的密码哈希行为
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        # 设置基本存储操作行为
        mock_storage.get.return_value = None
        mock_storage.list_owners.return_value = []
        mock_storage.has_duplicate.return_value = False
        mock_storage.set.return_value = True
        return mock_storage

    @pytest.fixture
    def manager(self, auth_manager, storage):
        manager = UserManager(auth_manager, storage)
        manager._storage.set.return_value = None
        return manager
    
    def test_create_user_success(self, manager):
        """测试成功创建用户"""
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "hashed_password"
        }
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser",
            password="password123"
        )
        
        assert result["success"] is True
        assert isinstance(result["user"], User)
        assert result["user"].username == "testuser"
        assert result["user"].email == "test@example.com"
        
    def test_create_user_duplicate_username(self, manager):
        """测试创建用户 - 用户名重复"""
        existing_user = User(
            user_id="existing",
            username="testuser",
            email="existing@example.com",
            password_hash="existing_password_hash",
            roles=[UserRole.USER],
            created_at=datetime.now(),
            require_password_change=False
        )
        manager._storage.has_duplicate.return_value = True
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser"
        )
        
        assert result["success"] is False
        assert "already exists" in result["error"]
        
    def test_create_user_with_random_password(self, manager):
        """测试创建用户 - 使用随机密码"""
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "hashed_password"
        }
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser"
        )
        
        assert result["success"] is True
        assert result["generated_password"] is not None
    
    def test_create_user_with_custom_roles(self, manager):
        """测试创建用户 - 指定角色"""
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "hashed_password"
        }
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            roles=[UserRole.OPERATOR, UserRole.USER]
        )
        
        assert result["success"] is True
        assert isinstance(result["user"], User)
        assert UserRole.OPERATOR in result["user"].roles
        assert UserRole.USER in result["user"].roles
    
    def test_create_user_password_hash_failure(self, manager):
        """测试创建用户 - 密码哈希失败"""
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": False,
            "error": "Invalid password format"
        }
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser",
            password="invalid_pwd"
        )
        
        assert result["success"] is False
        assert "Invalid password format" in result["error"]
    
    def test_create_user_duplicate_email(self, manager):
        """测试创建用户 - 邮箱重复"""
        existing_user = User(
            user_id="existing",
            username="other_user",
            email="test@example.com",
            password_hash="existing_password_hash",
            roles=[UserRole.USER],
            created_at=datetime.now(),
            require_password_change=False
        )
        manager._storage.has_duplicate.return_value = True
        
        result = manager.create_user(
            email="test@example.com",
            username="testuser"
        )
        
        assert result["success"] is False
        assert "already exists" in result["error"]
    
    def test_create_user_storage_failure(self, manager):
        """测试创建用户 - 存储失败"""
        # 设置 mock 行为
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "hashed_password"
        }
        
        # 模拟存储失败
        manager._storage.set.side_effect = Exception("Storage error")
        
        # 调用创建用户方法
        result = manager.create_user(
            email="test@example.com",
            username="testuser",
            password="password123"
        )
        
        # 验证结果
        assert result["success"] is False
        assert "Storage error" in str(result.get("error"))

    def test_create_user_with_custom_id(self, manager):
        """测试创建用户 - 指定用户ID"""
        # 设置 mock 行为
        manager._storage.has_duplicate.return_value = False
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "hashed_password"
        }
        
        # 记录初始调用次数（考虑到 ensure_admin_user 的调用）
        initial_call_count = manager._storage.set.call_count
        
        # 使用自定义 ID 创建用户
        custom_id = "custom_user_123"
        result = manager.create_user(
            email="test@example.com",
            username="testuser",
            password="password123",
            user_id=custom_id
        )
        
        # 验证结果
        assert result["success"] is True
        assert result["user"].user_id == custom_id
        assert result["user"].username == "testuser"
        
        # 验证存储调用
        assert manager._storage.set.call_count == initial_call_count + 1
        last_call = manager._storage.set.call_args
        assert last_call[1]['owner_id'] == custom_id
        created_user = last_call[0][0]
        assert isinstance(created_user, User)
        assert created_user.user_id == custom_id

class TestUserQueries:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        # 设置默认的密码哈希行为
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        # 设置基本存储操作行为
        mock_storage.get.return_value = None
        mock_storage.list_owners.return_value = []
        mock_storage.has_duplicate.return_value = False
        mock_storage.set.return_value = True
        return mock_storage

    @pytest.fixture
    def manager(self, auth_manager, storage):
        return UserManager(auth_manager, storage)
    
    def test_get_user_by_username(self, manager):
        """测试通过用户名获取用户 - 成功"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            roles={UserRole.USER}
        )
        manager._storage.list_owners.return_value = ["test123"]
        manager._storage.get.return_value = test_user
        
        result = manager.get_user_by_username("testuser")
        assert result == test_user
        
    def test_get_user_by_username_not_found(self, manager):
        """测试通过用户名获取用户 - 用户不存在"""
        # 设置空的用户列表
        manager._storage.list_owners.return_value = []
        manager._storage.get.return_value = None
        
        result = manager.get_user_by_username("nonexistent")
        assert result is None
        
    def test_get_user_by_username_storage_error(self, manager):
        """测试通过用户名获取用户 - 存储错误"""
        # 模拟存储异常
        manager._storage.list_owners.side_effect = Exception("Storage error")
        
        result = manager.get_user_by_username("testuser")
        assert result is None
        
    def test_get_user_by_username_multiple_users(self, manager):
        """测试通过用户名获取用户 - 多用户场景"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            roles={UserRole.USER}
        )
        other_user = User(
            user_id="other456",
            username="other",
            email="other@example.com",
            roles={UserRole.USER}
        )
        
        # 模拟多个用户存在的情况
        manager._storage.list_owners.return_value = ["test123", "other456"]
        def get_mock(owner_id):
            return test_user if owner_id == "test123" else other_user
        manager._storage.get.side_effect = get_mock
        
        result = manager.get_user_by_username("testuser")
        assert result == test_user
        
    def test_get_user_by_email(self, manager):
        """测试通过邮箱获取用户 - 成功"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            roles={UserRole.USER}
        )
        manager._storage.list_owners.return_value = ["test123"]
        manager._storage.get.return_value = test_user
        
        result = manager.get_user_by_email("test@example.com")
        assert result == test_user
        
    def test_get_user_by_email_not_found(self, manager):
        """测试通过邮箱获取用户 - 用户不存在"""
        manager._storage.list_owners.return_value = []
        manager._storage.get.return_value = None
        
        result = manager.get_user_by_email("nonexistent@example.com")
        assert result is None
        
    def test_get_user_by_email_storage_error(self, manager):
        """测试通过邮箱获取用户 - 存储错误"""
        manager._storage.list_owners.side_effect = Exception("Storage error")
        
        result = manager.get_user_by_email("test@example.com")
        assert result is None
        
    def test_get_user_by_email_case_insensitive(self, manager):
        """测试通过邮箱获取用户 - 大小写不敏感"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            roles={UserRole.USER}
        )
        
        # 设置 mock 行为
        manager._storage.list_owners.return_value = ["test123"]
        manager._storage.get.return_value = test_user
        
        # 使用不同大小写组合测试
        test_cases = [
            "TEST@example.com",
            "test@EXAMPLE.com",
            "Test@Example.Com"
        ]
        
        for test_email in test_cases:
            result = manager.get_user_by_email(test_email)
            assert result == test_user, f"Failed to match email: {test_email}"

class TestPasswordManagement:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        mock_auth.verify_password.return_value = {
            "success": True
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        mock_storage.get.return_value = None
        mock_storage.list_owners.return_value = []
        mock_storage.has_duplicate.return_value = False
        mock_storage.set.return_value = True
        return mock_storage

    @pytest.fixture
    def test_user(self):
        """创建测试用户"""
        return User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            password_hash="old_hash",
            roles={UserRole.USER},
            created_at=datetime.now(),
            require_password_change=False,
            last_password_change=None
        )

    @pytest.fixture
    def manager(self, auth_manager, storage):
        """创建用户管理器"""
        manager = UserManager(auth_manager, storage)
        # 重置所有 mock 的调用记录
        storage.reset_mock()
        return manager

    def test_verify_user_password_success(self, manager, test_user):
        """测试密码验证 - 成功"""
        # 模拟用户查找 - 使用 list_owners 和 get 组合
        manager._storage.list_owners.return_value = [test_user.user_id]
        manager._storage.get.return_value = test_user
        
        # 确保验证密码成功
        manager.auth_manager.verify_password.return_value = {
            "success": True
        }

        result = manager.verify_user_password("testuser", "password123")
        print(f"Debug - Result: {result}")  # 添加调试信息
        
        assert result["success"] is True

    def test_verify_user_password_invalid(self, manager, test_user):
        """测试密码验证 - 密码错误"""
        # 模拟用户查找
        manager._storage.list_owners.return_value = [test_user.user_id]
        manager._storage.get.return_value = test_user
        manager.auth_manager.verify_password.return_value = {
            "success": False,
            "error": "Invalid password"
        }

        result = manager.verify_user_password("testuser", "wrong_password")
        assert result["success"] is False
        assert "Invalid password" in result["error"]

    def test_verify_user_password_storage_error(self, manager, test_user):
        """测试密码验证 - 存储错误"""
        # 模拟 get_user_by_username 方法的行为
        def mock_get_user_by_username(username):
            print(f">>> Mock: 尝试获取用户名 {username}")
            raise Exception("Storage error")
        
        # 替换 get_user_by_username 方法
        with patch.object(manager, 'get_user_by_username', side_effect=mock_get_user_by_username):
            result = manager.verify_user_password("testuser", "password123")
            
            # 验证结果
            assert result["success"] is False
            assert result["user"] is None
            assert result["require_password_change"] is False
            assert "Storage error" in result["error"]
            
            # verify_password 不应该被调用，因为获取用户就失败了
            manager.auth_manager.verify_password.assert_not_called()

    def test_change_password_success(self, manager, test_user):
        """测试修改密码 - 成功"""
        manager._storage.get.return_value = test_user
        manager.auth_manager.verify_password.return_value = {"success": True}
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "new_hash"
        }

        result = manager.change_password(
            "test123", 
            "old_password", 
            "new_password"
        )
        
        assert result["success"] is True
        assert result["error"] is None
        assert test_user.password_hash == "new_hash"
        assert test_user.require_password_change is False
        assert test_user.last_password_change is not None
        manager._storage.set.assert_called_once_with(test_user, owner_id="test123")

    def test_reset_password_success(self, manager, test_user):
        """测试重置密码 - 成功"""
        manager._storage.get.return_value = test_user
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "new_hash"
        }

        result = manager.reset_password("test123", "new_password")
        
        assert result["success"] is True
        assert result["error"] is None
        assert test_user.password_hash == "new_hash"
        assert test_user.require_password_change is True
        assert test_user.last_password_change is not None
        manager._storage.set.assert_called_once_with(test_user, owner_id="test123")

    def test_reset_password_storage_error(self, manager, test_user):
        """测试重置密码 - 存储错误"""
        manager._storage.get.return_value = test_user
        manager.auth_manager.hash_password.return_value = {
            "success": True,
            "hash": "new_hash"
        }
        manager._storage.set.side_effect = Exception("Storage error")

        result = manager.reset_password("test123", "new_password")

        # 验证结果
        assert result["success"] is False
        assert "Storage error" in result["error"]
        
        # 验证 storage.set 被调用
        manager._storage.set.assert_called_once_with(test_user, owner_id="test123")
        
        # 注意：当前实现不会回滚状态，所以用户对象会保持修改后的状态
        assert test_user.password_hash == "new_hash"
        assert test_user.require_password_change is True
        assert test_user.last_password_change is not None

class TestRoleManagement:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        mock_auth.verify_password.return_value = {
            "success": True
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        mock_storage.get.return_value = None
        mock_storage.list_owners.return_value = []
        mock_storage.has_duplicate.return_value = False
        mock_storage.set.return_value = True
        return mock_storage

    @pytest.fixture
    def test_user(self):
        """创建测试用户"""
        return User(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            password_hash="old_hash",
            roles={UserRole.USER},
            created_at=datetime.now(),
            require_password_change=False,
            last_password_change=None
        )

    @pytest.fixture
    def manager(self, auth_manager, storage):
        return UserManager(auth_manager, storage)

    def test_update_user_roles_success(self, manager):
        """测试更新用户角色 - 成功"""
        test_user = User(
            user_id="test123",
            username="testuser",
            roles={UserRole.USER}
        )
        manager._storage.get.return_value = test_user

        result = manager.update_user_roles(
            "test123", 
            ["admin", "operator"]
        )
        
        assert result["success"] is True
        assert UserRole.ADMIN in test_user.roles
        assert UserRole.OPERATOR in test_user.roles

    def test_update_user_roles_invalid_role(self, manager):
        """测试更新用户角色 - 无效角色"""
        test_user = User(
            user_id="test123",
            username="testuser",
            roles={UserRole.USER}
        )
        manager._storage.get.return_value = test_user

        result = manager.update_user_roles(
            "test123", 
            ["invalid_role"]
        )
        
        assert result["success"] is False
        assert "Invalid role" in result["error"]

class TestUserUpdateAndDeletion:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        mock_storage.get.return_value = None
        mock_storage.set.return_value = True
        mock_storage.delete.return_value = True
        return mock_storage

    @pytest.fixture
    def manager(self, auth_manager, storage):
        return UserManager(auth_manager, storage)

    def test_update_user_success(self, manager):
        """测试更新用户信息 - 成功"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="old@example.com",
            password_hash="old_hash",
            roles={UserRole.USER},
            created_at=datetime.now(),
            require_password_change=False,
            last_password_change=None
        )
        manager._storage.get.return_value = test_user

        result = manager.update_user(
            "test123",
            email="new@example.com",
            username="newuser"
        )
        
        assert result["success"] is True
        assert test_user.email == "new@example.com"
        assert test_user.username == "newuser"
        manager._storage.set.assert_called_once_with(test_user, owner_id="test123")

    def test_update_user_not_found(self, manager):
        """测试更新用户信息 - 用户不存在"""
        manager._storage.get.return_value = None

        result = manager.update_user(
            "test123",
            email="new@example.com"
        )
        
        assert result["success"] is False
        assert "User not found" in result["error"]
        manager._storage.set.assert_not_called()

    def test_update_user_storage_error(self, manager):
        """测试更新用户信息 - 存储错误"""
        test_user = User(
            user_id="test123",
            username="testuser",
            email="old@example.com",
            password_hash="old_hash",
            roles={UserRole.USER},
            created_at=datetime.now(),
            require_password_change=False,
            last_password_change=None
        )
        manager._storage.get.return_value = test_user
        manager._storage.set.side_effect = Exception("Storage error")

        result = manager.update_user(
            "test123",
            email="new@example.com"
        )
        
        assert result["success"] is False
        assert "Storage error" in result["error"]

    def test_delete_user_success(self, manager):
        """测试删除用户 - 成功"""
        manager._storage.delete.return_value = True

        result = manager.delete_user("test123")
        
        assert result["success"] is True
        manager._storage.delete.assert_called_once_with(
            owner_id="test123"
        )

    def test_delete_user_not_found(self, manager):
        """测试删除用户 - 用户不存在"""
        manager._storage.delete.return_value = False

        result = manager.delete_user("test123")
        
        assert result["success"] is False
        assert "User not found" in result["error"]

    def test_delete_user_storage_error(self, manager):
        """测试删除用户 - 存储错误"""
        manager._storage.delete.side_effect = Exception("Storage error")

        result = manager.delete_user("test123")
        
        assert result["success"] is False
        assert "Storage error" in result["error"]

class TestAccessControl:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """每个测试方法执行前的设置"""
        # 清理测试数据目录
        import shutil
        from illufly.config import get_env
        test_dir = Path(get_env("ILLUFLY_FASTAPI_USERS_PATH"))
        if test_dir.exists():
            shutil.rmtree(test_dir)

    @pytest.fixture
    def auth_manager(self):
        """创建认证管理器的 mock"""
        mock_auth = Mock(spec=AuthManager)
        mock_auth.hash_password.return_value = {
            "success": True,
            "hash": "default_hashed_password"
        }
        return mock_auth

    @pytest.fixture
    def storage(self):
        """创建存储的 mock"""
        mock_storage = Mock()
        mock_storage.get.return_value = None
        mock_storage.set.return_value = True
        mock_storage.delete.return_value = True
        return mock_storage

    @pytest.fixture
    def manager(self, auth_manager, storage):
        return UserManager(auth_manager, storage)
        
    @pytest.fixture
    def test_user(self):
        return User(
            user_id="user123",
            username="testuser",
            email="test@example.com",
            password_hash="dummy_hash",
            roles={UserRole.USER}
        )

    def test_can_access_user_same_user(self, manager):
        """测试用户访问权限 - 同一用户"""
        assert manager.can_access_user("user123", "user123") is True

    def test_can_access_user_admin(self, manager):
        """测试用户访问权限 - 管理员"""
        manager._admin_ids.add("admin123")
        assert manager.can_access_user("user123", "admin123") is True

    def test_can_access_user_unauthorized(self, manager):
        """测试用户访问权限 - 未授权"""
        assert manager.can_access_user("user123", "other123") is False

    def test_get_user_same_user(self, manager, storage, test_user):
        """测试获取用户信息 - 同一用户"""
        # 设置 storage.get 的返回值
        storage.get.return_value = test_user
        
        result = manager.get_user(test_user.user_id, test_user.user_id)
        assert result is not None
        assert result.user_id == test_user.user_id
        # 验证 storage.get 被正确调用
        storage.get.assert_called_once_with(owner_id=test_user.user_id)

    def test_get_user_admin(self, manager, storage, test_user):
        """测试获取用户信息 - 管理员访问"""
        admin_id = "admin123"
        manager._admin_ids.add(admin_id)
        # 设置 storage.get 的返回值
        storage.get.return_value = test_user
        
        result = manager.get_user(test_user.user_id, admin_id)
        assert result is not None
        assert result.user_id == test_user.user_id
        # 验证 storage.get 被正确调用
        storage.get.assert_called_once_with(owner_id=test_user.user_id)

    def test_get_user_unauthorized(self, manager, storage, test_user):
        """测试获取用户信息 - 未授权访问"""
        # 设置 storage.get 的返回值，虽然这里不会被调用
        storage.get.return_value = test_user
        
        result = manager.get_user(test_user.user_id, "other123")
        assert result is None
        # 验证 storage.get 没有被调用
        storage.get.assert_not_called()

    def test_get_user_nonexistent(self, manager):
        """测试获取不存在的用户信息"""
        result = manager.get_user("nonexistent", "nonexistent")
        assert result is None
