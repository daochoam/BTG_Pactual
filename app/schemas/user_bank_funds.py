import uuid
from enum import Enum
from decimal import Decimal
from app.models import DynamoModel, GSI
from app.schemas.bank_funds import CurrencyEnum
from app.utils.time import get_current_time

class UserBankFundsSchema(DynamoModel):
    table_name = "UserBankFunds"
    partition_key = "id"
    indexes = (GSI("user_id"), GSI("bank_funds_id"))

    class StatusEnum(str, Enum):
      OPEN = "OPEN"
      CLOSED = "CLOSED"

    def __init__(self, user_id: str, bank_funds_id: str, amount: float, currency: CurrencyEnum = CurrencyEnum.COL, status: 'UserBankFundsSchema.StatusEnum' = StatusEnum.OPEN, created_at: str = None):
      self.id = str(uuid.uuid4())
      self.user_id = user_id
      self.bank_funds_id = bank_funds_id
      self.currency = currency
      self.amount = amount
      self.status = status
      self.created_at = created_at or get_current_time()
      self.updated_at = get_current_time()

      if not self.currency or self.currency not in list(CurrencyEnum):
          self.currency = CurrencyEnum.COL

      if self.amount < 0:
          self.amount = Decimal("0.0")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "user_id": self.user_id,
            "bank_funds_id": self.bank_funds_id,
            "currency": self.currency,
            "amount": self.amount,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            user_id=data["user_id"],
            bank_funds_id=data["bank_funds_id"],
            status=data.get("status", "OPEN"),
            amount=Decimal(data.get("amount", 0)),
            created_at=data.get("created_at")
        )

user_bank_funds_db = UserBankFundsSchema.table
__all__ = ["user_bank_funds_db", "UserBankFundsSchema"]