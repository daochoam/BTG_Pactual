import uuid
from app.models import GSI
from app.schemas.user_bank_funds import UserBankFundsSchema

from app.utils.time import get_current_time


class UserBankFundsAuditSchema(UserBankFundsSchema):
    # Hereda el comportamiento pero vive en su propia tabla.
    table_name = "UserBankFundsAudit"
    partition_key = "id"
    indexes = (GSI("parent_id"), GSI("user_id"))

    # Llamamos al constructor padre con los campos que necesita
    def __init__(self, parent: UserBankFundsSchema):
        super().__init__(user_id=parent.user_id, bank_funds_id=parent.bank_funds_id, status=parent.status, amount=parent.amount, created_at=parent.created_at)
        self.id = str(uuid.uuid4())
        self.parent_id = parent.id
        self.created_at = get_current_time()
      
    def to_dict(self):
        base_dict = super().to_dict()
        base_dict.update({
            "id": self.id,
            "parent_id": self.parent_id,
            "created_at": self.created_at
        })
        return base_dict
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            parent=UserBankFundsSchema.from_dict(data["parent"])
        )

user_bank_funds_audit_db = UserBankFundsAuditSchema.table
__all__ = ["user_bank_funds_audit_db", "UserBankFundsAuditSchema"]