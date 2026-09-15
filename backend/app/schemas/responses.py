from typing import List, Optional
from pydantic import BaseModel, Field


class SubSignalsSchema(BaseModel):
    structural_strength: float = Field(..., description="0-1 score for temporal & topological cohesion")
    sender_freshness: float = Field(..., description="0-1 score for counterparty account freshness")
    amount_band_signal: float = Field(..., description="0-1 score for smurfing/threshold amount banding")
    receiver_dampening: float = Field(..., description="0 to -1 dampening for known merchants")


class AccountRiskResponse(BaseModel):
    account_id: str
    upi_id: str
    risk_score: float
    risk_bucket: str
    evidence_summary: str
    pattern_type: Optional[str] = None
    cluster_id: Optional[str] = None
    sub_signals: SubSignalsSchema


class SimulateTransactionResponse(BaseModel):
    decision: str
    payer_event_id: int
    risk_score: float
    risk_bucket: str
    evidence_summary: str
    options: Optional[List[str]] = None


class ResolveTransactionResponse(BaseModel):
    status: str
    payer_event_id: int
    user_action: str


class CaseResponse(BaseModel):
    id: int
    account_id: str
    pattern_type: str
    cluster_id: Optional[str] = None
    risk_score: float
    risk_bucket: str
    evidence_summary: str
    status: str
    created_at: Optional[str] = None
    upi_id: Optional[str] = ""


class NetworkClusterResponse(BaseModel):
    cluster_id: str
    highest_risk_score: float
    highest_risk_bucket: str
    account_count: int
    total_transaction_amount: float
    cases: List[CaseResponse]


class TraceNodeResponse(BaseModel):
    account_id: str
    upi_id: str
    account_type: str
    account_age_days: int


class TraceEdgeResponse(BaseModel):
    transaction_id: str
    sender_id: str
    receiver_id: str
    amount: float
    timestamp: str
    pattern_type: str
    cluster_id: str


class TraceResponse(BaseModel):
    center_account_id: str
    center_upi_id: str
    hops: int
    nodes: List[TraceNodeResponse]
    edges: List[TraceEdgeResponse]


class RootResponse(BaseModel):
    service: str
    status: str
    nodes_loaded: int
    edges_loaded: int
    findings_cached: int
