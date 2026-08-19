import uuid
from enum import Enum
from decimal import Decimal
from app.models import DynamoModel, GSI
from app.schemas.bank_funds import CurrencyEnum
from app.utils.time import get_current_time

class UserSchema(DynamoModel):
    """
    Schema para representar un usuario en DynamoDB.
    """

    table_name = "Users"
    partition_key = "id"
    indexes = (GSI("email"), GSI("nit"))

    class RoleEnum(str, Enum):
        USER = "USER"
        ADMIN = "ADMIN"

    def __init__(self, nit: str, name: str, last_name: str, email: str, phone: str, role: RoleEnum=RoleEnum.USER, amount: float=0, currency: CurrencyEnum=CurrencyEnum.COL, id:str=None, created_at: str=None):
        self.id = id or str(uuid.uuid4())
        self.nit = nit
        self.name = name
        self.last_name = last_name
        self.email = email
        self.phone = phone
        self.role = role
        self.amount = amount
        self.currency = currency
        self.verified = False
        self.created_at = created_at or get_current_time()
        self.updated_at = get_current_time()

        if self.currency not in list(CurrencyEnum):
            self.currency = CurrencyEnum.COL
            
        if self.role not in list(UserSchema.RoleEnum):
            self.role = UserSchema.RoleEnum.USER
        
        if self.role.upper() == UserSchema.RoleEnum.USER:
            self.amount = Decimal("500000")
        elif self.role.upper() == UserSchema.RoleEnum.ADMIN:
            self.amount = Decimal("0")

    def to_dict(self):
        return {
            "id": self.id,
            "nit": self.nit,
            "name": self.name,
            "last_name": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "amount": self.amount,
            "currency": self.currency,
            "verified": self.verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            nit=data["nit"],
            name=data["name"],
            last_name=data["last_name"],
            email=data["email"],
            phone=data["phone"],
            role=UserSchema.RoleEnum(data["role"]),
            amount=data["amount"],
            currency=CurrencyEnum(data["currency"]),
            verified=data["verified"],
            created_at=data["created_at"],
            updated_at=data["updated_at"]
        )

users_db = UserSchema.table
__all__ = ["users_db", "UserSchema"]
