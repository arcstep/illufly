from ..common.storage import BaseStorage
from .models import User

class UserStorage(BaseStorage[User]):
    def _serialize(self, user: User) -> Dict[str, Any]:
        return user.to_dict(include_sensitive=True)

    def _deserialize(self, data: Dict[str, Any]) -> User:
        return User.from_dict(data) 