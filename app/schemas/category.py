import uuid
from app.models import DynamoModel
from app.utils.time import get_current_time

class CategorySchema(DynamoModel):
    """
    Schema para representar una categoría en DynamoDB.
    """

    table_name = "Categories"
    partition_key = "id"

    def __init__(self, user_created: str, name: str, description: str=None, user_updated: str=None, created_at: str=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description if description is not None else ""
        self.user_created = user_created
        self.user_updated = user_updated or user_created
        self.created_at = created_at or get_current_time()
        self.updated_at = get_current_time()


    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "user_created": self.user_created,
            "user_updated": self.user_updated,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            user_created=data["user_created"],
            description=data["description"],
            user_updated=data["user_updated"],
            created_at=data["created_at"],
            updated_at=data["updated_at"]
        )

categories_db = CategorySchema.table
__all__ = ["categories_db", "CategorySchema"]