import uuid
from decimal import Decimal
from enum import Enum
from app.models import DynamoModel, GSI
from app.utils.time import get_current_time

class CurrencyEnum(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    COL = "COP"
    BRA = "BRL"

class BankFundsSchema(DynamoModel):
    table_name = "BankFunds"
    partition_key = "id"
    indexes = (GSI("category_id"),)

    def __init__(self, name: str, category_id: str, min_amount: float, currency: CurrencyEnum = CurrencyEnum.COL, user_created: str = None, user_updated: str = None, created_at: str = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.category_id = category_id
        self.currency = currency
        self.min_amount = Decimal(min_amount)
        self.user_created = user_created
        self.user_updated = user_updated or user_created
        self.created_at = created_at or get_current_time()
        self.updated_at = get_current_time()

        if not currency or currency not in list(CurrencyEnum):
            self.currency = CurrencyEnum.COL
        
        if min_amount < 0:
            self.min_amount = Decimal("0.0")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category_id": self.category_id,
            "min_amount": self.min_amount,
            "currency": self.currency,
            "user_created": self.user_created,
            "user_updated": self.user_updated,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            name=data["name"],
            category_id=data["category_id"],
            min_amount=data["min_amount"],
            user_created=data["user_created"],
            currency=CurrencyEnum(data["currency"]),
            user_updated=data["user_updated"],
            created_at=data["created_at"],
            updated_at=data["updated_at"]
        )

bank_funds_db = BankFundsSchema.table
__all__ = ["bank_funds_db", "BankFundsSchema"]