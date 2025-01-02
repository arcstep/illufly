
class PathError(Exception):
    """路径错误的基类"""
    def __init__(self, message: str, path: str = None, namespace: str = None):
        self.message = message
        self.path = path
        self.namespace = namespace
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [self.message]
        if self.path:
            parts.append(f"路径: {self.path}")
        if self.namespace:
            parts.append(f"命名空间: {self.namespace}")
        return " | ".join(parts)

class PathNotFoundError(PathError):
    """路径不存在错误"""
    pass

class PathValidationError(PathError):
    """路径验证错误"""
    pass

class PathTypeError(PathError):
    """路径类型错误"""
    def __init__(self, message: str, expected_type: str = None, actual_type: str = None, 
                 path: str = None, namespace: str = None):
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(message, path, namespace)

    def _format_message(self) -> str:
        parts = [self.message]
        if self.expected_type:
            parts.append(f"期望类型: {self.expected_type}")
        if self.actual_type:
            parts.append(f"实际类型: {self.actual_type}")
        if self.path:
            parts.append(f"路径: {self.path}")
        if self.namespace:
            parts.append(f"命名空间: {self.namespace}")
        return " | ".join(parts)