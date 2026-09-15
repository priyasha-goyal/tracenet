from pydantic import BaseModel, Field


class SimulateTransactionRequest(BaseModel):
    payer_account_id: str = Field(..., description="Account ID or UPI ID of the sender")
    payee_account_id: str = Field(..., description="Account ID or UPI ID of the recipient")
    amount: float = Field(..., gt=0, description="Transaction amount")


class ResolveTransactionRequest(BaseModel):
    action: str = Field(..., description="Action taken: proceeded_normally, cancelled, or overrode_warning")


class CaseActionRequest(BaseModel):
    action: str = Field(..., description="Case action: mark_legitimate or escalate")
